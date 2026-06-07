"""
pipeline/canary_deployer.py
----------------------------
Deploys a new SageMaker model endpoint version using a canary (blue/green) strategy.

Deployment flow:
  1. Create a new endpoint configuration pointing to the approved model package
  2. Update the endpoint — SageMaker routes 10% of traffic to the new config
  3. Watch the CloudWatch error-rate alarm for ALARM_WINDOW_MINUTES
  4a. If alarm triggers → roll back to previous endpoint config automatically
  4b. If alarm stays green → shift 100% traffic to the new config

This pattern ensures that a faulty model version cannot fully replace the
production model before its behaviour is validated on live traffic.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import boto3

logger = logging.getLogger(__name__)

ALARM_WINDOW_MINUTES = int(os.environ.get("ALARM_WINDOW_MINUTES", "30"))
POLL_INTERVAL_SECONDS = int(os.environ.get("POLL_INTERVAL_SECONDS", "60"))
CANARY_TRAFFIC_PERCENT = int(os.environ.get("CANARY_TRAFFIC_PERCENT", "10"))


@dataclass
class DeploymentResult:
    success: bool
    endpoint_name: str
    new_config_name: str
    previous_config_name: str
    rolled_back: bool
    message: str


class CanaryDeployer:
    def __init__(self) -> None:
        self._sm = boto3.client("sagemaker", region_name=os.environ.get("AWS_REGION", "eu-west-1"))
        self._cw = boto3.client("cloudwatch", region_name=os.environ.get("AWS_REGION", "eu-west-1"))

    def deploy(
        self,
        endpoint_name: str,
        model_package_arn: str,
        new_config_name: str,
        alarm_name: str,
    ) -> DeploymentResult:
        """
        Execute a canary deployment of model_package_arn to endpoint_name.

        Args:
            endpoint_name:     Existing production SageMaker endpoint name.
            model_package_arn: The approved model package to deploy.
            new_config_name:   Name for the new endpoint configuration.
            alarm_name:        CloudWatch alarm to watch for rollback signal.
        """
        previous_config = self._get_current_endpoint_config(endpoint_name)
        logger.info(
            "Starting canary deployment: endpoint=%s new_config=%s previous=%s",
            endpoint_name, new_config_name, previous_config,
        )

        # Step 1: Create new endpoint configuration
        self._create_endpoint_config(new_config_name, model_package_arn, previous_config)

        # Step 2: Update endpoint with canary routing
        self._update_endpoint_canary(endpoint_name, new_config_name, previous_config)
        self._wait_for_endpoint_in_service(endpoint_name)

        # Step 3: Monitor for ALARM_WINDOW_MINUTES
        logger.info("Canary active — monitoring alarm '%s' for %d minutes", alarm_name, ALARM_WINDOW_MINUTES)
        alarm_triggered = self._monitor_alarm(alarm_name, ALARM_WINDOW_MINUTES)

        if alarm_triggered:
            # Step 4a: Roll back
            logger.warning("Alarm triggered — rolling back to %s", previous_config)
            self._rollback(endpoint_name, previous_config)
            return DeploymentResult(
                success=False,
                endpoint_name=endpoint_name,
                new_config_name=new_config_name,
                previous_config_name=previous_config,
                rolled_back=True,
                message=f"Rolled back: alarm '{alarm_name}' triggered during canary window",
            )

        # Step 4b: Full traffic shift
        logger.info("Canary healthy — shifting 100%% traffic to %s", new_config_name)
        self._promote_canary(endpoint_name, new_config_name)
        return DeploymentResult(
            success=True,
            endpoint_name=endpoint_name,
            new_config_name=new_config_name,
            previous_config_name=previous_config,
            rolled_back=False,
            message="Deployment successful — 100% traffic on new model version",
        )

    def _get_current_endpoint_config(self, endpoint_name: str) -> str:
        response = self._sm.describe_endpoint(EndpointName=endpoint_name)
        return response["EndpointConfigName"]

    def _create_endpoint_config(
        self, config_name: str, model_package_arn: str, previous_config: str
    ) -> None:
        # Get the previous config's production variants to inherit instance type etc.
        prev = self._sm.describe_endpoint_config(EndpointConfigName=previous_config)
        variant = prev["ProductionVariants"][0].copy()
        variant["ModelName"] = self._create_model_from_package(model_package_arn, config_name)
        variant["VariantName"] = "primary"
        variant["InitialVariantWeight"] = CANARY_TRAFFIC_PERCENT / 100

        self._sm.create_endpoint_config(
            EndpointConfigName=config_name,
            ProductionVariants=[variant],
        )

    def _create_model_from_package(self, model_package_arn: str, suffix: str) -> str:
        model_name = f"model-{suffix}"
        self._sm.create_model(
            ModelName=model_name,
            Containers=[{"ModelPackageName": model_package_arn}],
            ExecutionRoleArn=os.environ["SAGEMAKER_EXECUTION_ROLE_ARN"],
        )
        return model_name

    def _update_endpoint_canary(
        self, endpoint_name: str, new_config: str, previous_config: str
    ) -> None:
        self._sm.update_endpoint(
            EndpointName=endpoint_name,
            EndpointConfigName=new_config,
            RetainDeploymentConfig=False,
        )

    def _wait_for_endpoint_in_service(self, endpoint_name: str, timeout_seconds: int = 600) -> None:
        waiter = self._sm.get_waiter("endpoint_in_service")
        waiter.wait(EndpointName=endpoint_name, WaiterConfig={"Delay": 30, "MaxAttempts": timeout_seconds // 30})

    def _monitor_alarm(self, alarm_name: str, window_minutes: int) -> bool:
        """Poll the alarm state.  Returns True if it enters ALARM state."""
        end_time = time.monotonic() + window_minutes * 60
        while time.monotonic() < end_time:
            response = self._cw.describe_alarms(AlarmNames=[alarm_name])
            alarms = response.get("MetricAlarms", [])
            if alarms and alarms[0]["StateValue"] == "ALARM":
                return True
            time.sleep(POLL_INTERVAL_SECONDS)
        return False

    def _rollback(self, endpoint_name: str, previous_config: str) -> None:
        self._sm.update_endpoint(EndpointName=endpoint_name, EndpointConfigName=previous_config)
        self._wait_for_endpoint_in_service(endpoint_name)

    def _promote_canary(self, endpoint_name: str, new_config: str) -> None:
        """Already on new config — just ensure variant weight is 1.0."""
        self._sm.update_endpoint_weights_and_capacities(
            EndpointName=endpoint_name,
            DesiredWeightsAndCapacities=[{"VariantName": "primary", "DesiredWeight": 1.0}],
        )
