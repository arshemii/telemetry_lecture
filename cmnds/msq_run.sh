docker run -d \
  --name mosquitto \
  --network smartcollar_network \
  --restart unless-stopped \
  -p 1883:1883 \
  -v "$PWD/broker/mosquitto.conf:/mosquitto/config/mosquitto.conf:ro" \
  -v "$PWD/broker/passwords:/mosquitto/config/passwords:ro" \
  -v smartcollar_vol_broker:/mosquitto/data \
  eclipse-mosquitto:latest
