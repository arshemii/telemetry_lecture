0. Create a network and volumes with names:
smartcollar_network
smartcollar_vol_broker
smartcollar_vol_mongo

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


