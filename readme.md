0. Create a network and volumes with names:
smartcollar_network
smartcollar_vol_broker
smartcollar_vol_mongo
smartcollar_vol_dynamo

Create passwords for environmental variabls using:
openssl rand -hex 24 or 32

--------------------------------------------------------------------------------------------------------------------------------------------------
1. MQTT Broker starting
Open a terminal, source the environment using:

set -a
source .env
set +a

the run blow to generate password.

docker run --rm -it \
  -v "$PWD/broker:/mosquitto/config" \
  eclipse-mosquitto:latest \
  mosquitto_passwd -c \
  /mosquitto/config/passwords \
  "$MQTT_USER"
  
 
after that use:
sudo chmod 644 broker/passwords

And now you can run mosquitto:
docker run -d \
  --name mosquitto \
  --network smartcollar_network \
  --restart unless-stopped \
  -p 1883:1883 \
  -v "$PWD/broker/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" \
  -v "$PWD/broker/passwords:/mosquitto/config/passwords:ro" \
  -v smartcollar_vol_broker:/mosquitto/data \
  eclipse-mosquitto:latest
  
Checl logs if it is initialized correctly:
docker logs mosquitto
------------------- TEST --------------------------
Subscribe with another terminal sourced with .env

docker run --rm -it --network smartcollar_network eclipse-mosquitto:latest mosquitto_sub -h mosquitto -p 1883 -u "$MQTT_USER" -P "$MQTT_PASSWORD" -t "smartCollar/#" -v
  
publish with another terminal sourced with .env

docker run --rm \
  --network smartcollar_network \
  eclipse-mosquitto:latest \
  mosquitto_pub \
  -h mosquitto \
  -p 1883 \
  -u "$MQTT_USER" \
  -P "$MQTT_PASSWORD" \
  -t "smartCollar/collar-001/environment" \
  -m '{"temperature":24.5,"co2":510,"moisture":45}'


--------------------------------------------------------------------------------------------------------------------------------------------------
2. MongoDB starting
In the same terminal run:

docker run -d \
  --name collar-mongo \
  --network smartcollar_network \
  --restart unless-stopped \
  -e MONGO_INITDB_ROOT_USERNAME="$MONGO_ROOT_USER" \
  -e MONGO_INITDB_ROOT_PASSWORD="$MONGO_ROOT_PASSWORD" \
  -v smartcollar_vol_mongo:/data/db \
  mongodb/mongodb-community-server:8.0-ubi8-slim
  
  
check it with:
docker logs --tail 1 collar-mongo

--------------------------------------------------------------------------------------------------------------------------------------------------
3. Simulation
Considering you have built the simulation MCU docker, you will run:

docker run -d \
  --name collar-mcu \
  --network smartcollar_network \
  --restart unless-stopped \
  --env-file "$PWD/.env" \
  -e MQTT_HOST=mosquitto \
  -e SIM_INITIAL_BATTERY=95 \
  mcu:v1
  
And test the logs with
docker logs -f --tail 15 collar-mcu

Topics are:
21:00:00 MQTT publish queued | smartCollar/collar-001/motion
21:00:00 MQTT publish queued | smartCollar/collar-001/environment
21:00:00 MQTT publish queued | smartCollar/collar-001/location
21:00:00 MQTT publish queued | smartCollar/collar-001/battery


--------------------------------------------------------------------------------------------------------------------------------------------------
4. Worker (router)
First, we enter inside the shell of MongoDB with the password from .env

docker exec -it collar-mongo \
  mongosh \
  -u "$MONGO_ROOT_USER" \
  --authenticationDatabase admin \
  -p

un:
use smartcollar
it should switch to smart collar. then run:
db.adminCommand({ping: 1})
it shoud return 1:ok

Considering that the docker image of the worker is available, run:

docker run -d \
  --name router \
  --network smartcollar_network \
  --restart unless-stopped \
  --env-file "$PWD/.env" \
  -e MQTT_HOST=mosquitto \
  -e MONGO_HOST=collar-mongo \
  router:v1

verify by logging:
docker logs -f --tail 20 collar-db-worker

Check if really they are being stored:
Enter the MonGO server, then run:
use smartcollar
show collections

$ Latest 5 data
db.telemetry.find().sort({received_at: -1}).limit(5)

# show how many data came
db.telemetry.countDocuments({})

# show only environment
db.telemetry.find({
  type: "environment"
}).sort({received_at: -1}).limit(1)

# Showing the indexes of data
db.telemetry.getIndexes()


--------------------------------------------------------------------------------------------------------------------------------------------------
-------------------------------------------------------Modify worker - Add DynamoDB --------------------------------------------------------------
--------------------------------------------------------------------------------------------------------------------------------------------------

Preconditions:
	1. Having a docker image for DynamoDB local
	2. AWS CLI is installed or the docker image is pulled (docker is prefered)


1. Run the container using:
docker run -d \
  --name collar-dynamo \
  --network smartcollar_network \
  --restart unless-stopped \
  -v smartcollar_vol_dynamo:/home/dynamodblocal/data \
  --workdir /home/dynamodblocal \
  amazon/dynamodb-local:latest \
  -jar DynamoDBLocal.jar \
  -sharedDb \
  -dbPath ./data


We will run temporary containers using AWS CLI image. See below example:

docker run --rm \
  --network smartcollar_network \
  -e AWS_ACCESS_KEY_ID=local \
  -e AWS_SECRET_ACCESS_KEY=local \
  -e AWS_DEFAULT_REGION=eu-west-1 \
  -e AWS_MAX_ATTEMPTS=1 \
  -e AWS_PAGER="" \
  amazon/aws-cli:latest \
  dynamodb list-tables \
  --endpoint-url http://collar-dynamo:8000 \
  --cli-connect-timeout 3 \
  --cli-read-timeout 5 \
  --no-cli-pager

If it fails to show the table list (even empty), the issue belongs to the permissions of docker image on database.

2. Create a table using below container run (MongoDB can crate tables by dara being inserted from worker automatically):
docker run --rm \
  --network smartcollar_network \
  -e AWS_ACCESS_KEY_ID=local \
  -e AWS_SECRET_ACCESS_KEY=local \
  -e AWS_DEFAULT_REGION=eu-west-1 \
  -e AWS_PAGER="" \
  amazon/aws-cli:latest \
  dynamodb create-table \
  --table-name SmartCollarTelemetry \
  --attribute-definitions \
    AttributeName=device_id,AttributeType=S \
    AttributeName=timestamp,AttributeType=S \
  --key-schema \
    AttributeName=device_id,KeyType=HASH \
    AttributeName=timestamp,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST \
  --endpoint-url http://collar-dynamo:8000 \
  --no-cli-pager
  
  
Test the table by puting a data item:
docker run --rm \
  --network smartcollar_network \
  -e AWS_ACCESS_KEY_ID=local \
  -e AWS_SECRET_ACCESS_KEY=local \
  -e AWS_DEFAULT_REGION=eu-west-1 \
  amazon/aws-cli:latest \
  dynamodb put-item \
  --table-name SmartCollarTelemetry \
  --item '{
    "device_id": {"S": "collar-001"},
    "timestamp": {"S": "2026-10-18T10:00:00.000000+00:00"},
    "type": {"S": "environment"},
    "payload": {
      "M": {
        "temperature": {"N": "24.5"},
        "co2": {"N": "510"},
        "moisture": {"N": "45"}
      }
    }
  }' \
  --endpoint-url http://collar-dynamo:8000 \
  --no-cli-pager
  
Test the table if the data can be retievd:
docker run --rm \
  --network smartcollar_network \
  -e AWS_ACCESS_KEY_ID=local \
  -e AWS_SECRET_ACCESS_KEY=local \
  -e AWS_DEFAULT_REGION=eu-west-1 \
  amazon/aws-cli:latest \
  dynamodb get-item \
  --table-name SmartCollarTelemetry \
  --key '{
    "device_id": {"S": "collar-001"},
    "timestamp": {"S": "2026-10-18T10:00:00.000000+00:00"}
  }' \
  --endpoint-url http://collar-dynamo:8000 \
  --no-cli-pager
  
3. Worker modification (building a new image)
The purpose is to have a worker that can hanled three below modes to route data:

`STORAGE_MODE=mongo` -> Connect to MongoDB only (default)
`STORAGE_MODE=dynamo` -> Connect to DynamoDB Local only
`STORAGE_MODE=all` -> Connect to both databases

The new dockerfile and python script are rpepared and built. Run the container with all databases:

docker run -d \
  --name router \
  --network smartcollar_network \
  --restart unless-stopped \
  --env-file "$PWD/.env" \
  -e MQTT_HOST=mosquitto \
  -e MONGO_HOST=collar-mongo \
  -e DYNAMO_ENDPOINT=http://collar-dynamo:8000 \
  -e DYNAMO_TABLE=SmartCollarTelemetry \
  -e STORAGE_MODE=all \
  router:v2
  
-----> Checks for MongoDB already provided
-----> Checks for DynamoDB:
	docker run --rm \
		  --network smartcollar_network \
		  -e AWS_ACCESS_KEY_ID=local \
		  -e AWS_SECRET_ACCESS_KEY=local \
		  -e AWS_DEFAULT_REGION=eu-west-1 \
		  amazon/aws-cli:latest \
		  dynamodb scan \
		  --table-name SmartCollarTelemetry \
		  --select COUNT \
		  --endpoint-url http://collar-dynamo:8000 \
		  --no-cli-pager
		  
	It should show number of data
	

--------------------------------------------------------------------------------------------------------------------------------------------------
-------------------------------------------------------     Front-end ingestion     --------------------------------------------------------------
--------------------------------------------------------------------------------------------------------------------------------------------------
We use a SAM template.yaml file to tell which resources we need.
Lambda function as a python file also is prepared. The environment also is written for the lambda execution. Then, w can build using SAM, which it gave us a kind of lambda available, so we can execute it without wasting time.

The built is done in the same directory of the template and using:
sam build --use-container

Now, we start an HTTP server on the host Ubuntu using:
sam local start-api \
  --template-file .aws-sam/build/template.yaml \
  --docker-network smartcollar_network \
  --warm-containers LAZY \
  --port 3000
  
The server, upon a new HTTP requst, triggers the Lambda function by a temporary container to run the command. --docker-network smartcollar_network tells SAM which Docker network to attach its Lambda runtime containers to.

For every changes in in the build of SAM, we need to stop local API, rebuild, and start API again.

