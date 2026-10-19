# Optional AWS setup — use only after cost safeguards

1. In Billing, set budget alerts (for example $1 and $5) and enable Free Tier usage alerts where available.
2. Avoid launching instances solely for this project if your account may incur charges. Use existing resources or local synthetic mode first.
3. Use AWS IAM Identity Center/SSO or an instance role; never place access keys in source files or `.env`.
4. Read-only metrics policy should be limited to required CloudWatch read actions. Example actions to review with your instructor: `cloudwatch:GetMetricStatistics`, `cloudwatch:ListMetrics`, `cloudwatch:GetMetricData`. Do not attach `AdministratorAccess`.
5. Set `CLOUD_MODE=aws`, `AWS_REGION`, and `AWS_EC2_INSTANCE_ID` in `.env`; install `requirements-aws.txt`.
6. Run `POST /api/aws/sync`. This imports CPU metrics only. Memory/disk need CloudWatch Agent; app will not label absent metrics as live measurements.
7. For cost analysis, verify exact EC2 instance family/size, region, tenancy, OS and pricing from AWS pricing console; enter hourly USD rate as `EC2_HOURLY_PRICE_USD`. Unknown price stays unknown.
8. Lambda remediation is disabled by default. If used for a demo, scope the function to a single approved reversible action, enable CloudTrail, and set `ALLOW_LAMBDA_REMEDIATION=true` only after testing. Do not invoke production remediation.
9. Before enabling Lambda, set a strong random `REMEDIATION_APPROVAL_TOKEN` in the server environment and provide it only to the trusted operator. Never expose the token in frontend code or commit it.
10. Terminate demo resources when finished and review billing the next day.
