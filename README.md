# vi2mqtt
Connector between mqtt broker and vcontrold for Viessmann heating devices.

## docker-compose

```
services:
  vi2mqtt:
    image: clemens321/vi2mqtt
    volumes:
      - ./etc/vi2mqtt.conf:/etc/vi2mqtt.conf:ro
    environment:
      MQTT_USERNAME: "vi2mqtt"
      MQTT_PASSWORD: "${VI2MQTT_PASSWORD:-secret}"
    restart: unless-stopped
```

## Configuration
You can place a custom config file as `/etc/vi2mqtt.conf` inside the container or pass environment variables for some settings.

| Environment | Config path | Default | Description
| ----------- | ----------- | ------- | ---
| MQTT\_HOST     | mqtt.host     | mqtt | Hostname or ip address of mqtt broker
| MQTT\_PORT     | mqtt.port     | 1883 | Port of mqtt broker
| MQTT\_USERNAME | mqtt.username | none | Optional: Username to authenticate against mqtt broker
| MQTT\_PASSWORD | mqtt.password | none | Optional, but required with mqtt username
| *(none)* | mqtt.pub\_prefix | vcontrol | Prefix for topic to publish to
| VCONTROLD\_HOST | vcontrold.host | vcontrold | Hostname or ip address of vcontrold
| VCONTROLD\_PORT | vcontrold.port | 3002      | Port of vcontrold daemon
| PUBLISH\_INTERVAL  | publish.interval  | 60 | Default interval to trigger publish process
| PUBLISH\_MIN\_WAIT | publish.min\_wait | 10 | Minimum waiting time after a publish sequence in case it takes longer
| *(none)* | get\_commands | various   | commands to execute against vcontrold and publish to mqtt
