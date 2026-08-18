"""
Применяет CORS-политику к бакету и читает её обратно.

Политика приходит переменной `CORS_JSON` из `cors.json`, а не пишется здесь:
два экземпляра одной политики разъезжаются молча, и узнать об этом можно только
по неработающей загрузке.
"""
import json
import os
import sys

import boto3

rules = json.loads(os.environ["CORS_JSON"])

s3 = boto3.client(
    "s3",
    endpoint_url=os.environ["S3_ENDPOINT"],
    aws_access_key_id=os.environ["S3_ACCESS_KEY"],
    aws_secret_access_key=os.environ["S3_SECRET_KEY"],
    region_name=os.environ.get("S3_REGION", "ru-1"),
)
bucket = os.environ["S3_BUCKET"]

s3.put_bucket_cors(Bucket=bucket, CORSConfiguration=rules)

# Читаем обратно: put_bucket_cors отвечает 200 и на политику, которую провайдер
# потом не применит. Подтверждением считается только то, что вернул сервер.
applied = s3.get_bucket_cors(Bucket=bucket)["CORSRules"]
print("применено:", json.dumps(applied, ensure_ascii=False))
if not applied:
    sys.exit("политика не читается обратно — применение не подтверждено")
