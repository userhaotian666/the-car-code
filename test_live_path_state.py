import json
import time
import paho.mqtt.client as mqtt

MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
MQTT_USER = "hz_xulan"
MQTT_PW = "xunlan123456"

CAR_IP = "10.168.1.100"
TASK_ID = 61

topic = f"car/{CAR_IP}/task/live_path"

client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PW)
client.connect(MQTT_BROKER, MQTT_PORT, 60)

segments = [
    {
        "msg_id": "live_path_test_0",
        "version": "1.0",
        "timestamp": int(time.time()),
        "car_ip": CAR_IP,
        "data": {
            "task_id": TASK_ID,
            "segment_index": 0,
            "is_last": False,
            "points": [[1.21, 24.04], [12.6, 23.48], [21.44, 22.73]]
        }
    },
    {
        "msg_id": "live_path_test_1",
        "version": "1.0",
        "timestamp": int(time.time()),
        "car_ip": CAR_IP,
        "data": {
            "task_id": TASK_ID,
            "segment_index": 1,
            "is_last": False,
            "points": [[35.18, 21.97], [44.59, 19.53], [50.61, 14.26]]
        }
    },
    {
        "msg_id": "live_path_test_2",
        "version": "1.0",
        "timestamp": int(time.time()),
        "car_ip": CAR_IP,
        "data": {
            "task_id": TASK_ID,
            "segment_index": 2,
            "is_last": True,
            "points": [[60.2, 13.04], [71.3, 12.75], [77.23, 12.75]]
        }
    }
]

for payload in segments:
    client.publish(topic, json.dumps(payload, ensure_ascii=False))
    print("已发送:", payload)
    time.sleep(10)

client.disconnect()
