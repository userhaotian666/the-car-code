import os
import uuid

MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.emqx.io")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "hz_xulan")
MQTT_PW = os.getenv("MQTT_PW", "xunlan123456")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", "car/+/status")
MQTT_MISSION_REPORT_TOPIC = os.getenv("MQTT_MISSION_REPORT_TOPIC", "car/+/task/report")
MQTT_PATH_TOPIC_TEMPLATE = os.getenv("MQTT_PATH_TOPIC_TEMPLATE", "car/{car_ip}/task/path")
MQTT_TASK_CMD_TOPIC_TEMPLATE = os.getenv("MQTT_TASK_CMD_TOPIC_TEMPLATE", "car/{car_ip}/task/cmd")
MQTT_CLIENT_ID = os.getenv("MQTT_CLIENT_ID", f"backend_{uuid.uuid4().hex[:8]}")
SUPPORTED_VERSION = os.getenv("MQTT_VERSION", "1.0")
MQTT_RECONNECT_DELAY = float(os.getenv("MQTT_RECONNECT_DELAY", "3"))
MAX_RECENT_MSG_IDS = int(os.getenv("MQTT_RECENT_MSG_IDS", "1000"))
