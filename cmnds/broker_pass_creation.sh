docker run --rm -it \
  -v "$PWD/broker:/mosquitto/config" \
  eclipse-mosquitto:latest \
  mosquitto_passwd -c \
  /mosquitto/config/passwords \
  "$MQTT_USER"
