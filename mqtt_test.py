import json
import math
import os
import random
import time

import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "broker.emqx.io")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", "hz_xulan")
MQTT_PW = os.getenv("MQTT_PW", "xunlan123456")
CAR_IP = os.getenv("MQTT_CAR_IP", "10.168.1.100")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", f"car/{CAR_IP}/status")
MQTT_MISSION_REPORT_TOPIC = os.getenv("MQTT_MISSION_REPORT_TOPIC", f"car/{CAR_IP}/task/report")
TASK_ID = int(os.getenv("MQTT_TASK_ID", "1"))


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ 成功连接到 MQTT 服务器: {MQTT_BROKER}:{MQTT_PORT}")
    else:
        print(f"❌ 连接失败，返回码: {rc}")


def build_status_payload(step: int) -> dict:
    angle = step / 5
    speed = round(max(0.0, 0.6 * math.sin(step / 4) + random.uniform(-0.05, 0.05)), 2)
    battery = max(0, 100 - step // 6)
    gear = random.choice([1, 2, 3, 4])
    mode = random.choice([1, 2])
    timestamp = int(time.time())
    x = round(3.5 + math.cos(angle) * 1.2, 3)
    y = round(5.0 + math.sin(angle) * 1.2, 3)
    yaw = round((math.degrees(angle) + 360) % 360, 2)

    return {
        "car_ip": CAR_IP,
        "timestamp": timestamp,
        "longitude": x,
        "latitude": y,
        "yaw": yaw,
        "speed": speed,
        "mode": mode,
        "car_status": random.choice([0, 2, 3]),
        "work_status": random.choice([0, 1, 3, 4]),
        "battery": battery,
        "gear": gear,
    }


def build_mission_report_payload(step: int) -> dict:
    timestamp = int(time.time())
    phase = step % 12
    if phase < 3:
        task_status = 0
    elif phase < 9:
        task_status = 1
    else:
        task_status = 2

    return {
        "timestamp": timestamp,
        "car_id": CAR_IP,
        "task_id": TASK_ID,
        "task_status": task_status,
    }


def main():
    client = mqtt.Client(client_id=f"Mock_Car_{CAR_IP}")
    client.username_pw_set(MQTT_USER, MQTT_PW)
    client.on_connect = on_connect

    print("正在尝试连接 Broker...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    print("🚗 开始发送模拟状态消息 (按 Ctrl+C 停止)...\n")
    step = 0

    try:
        while True:
            status_payload = build_status_payload(step)
            status_payload_text = json.dumps(status_payload, ensure_ascii=False)
            client.publish(MQTT_TOPIC, status_payload_text)
            print(f"[发布] Topic: {MQTT_TOPIC} | Payload: {status_payload_text}")

            mission_payload = build_mission_report_payload(step)
            mission_payload_text = json.dumps(mission_payload, ensure_ascii=False)
            client.publish(MQTT_MISSION_REPORT_TOPIC, mission_payload_text)
            print(f"[发布] Topic: {MQTT_MISSION_REPORT_TOPIC} | Payload: {mission_payload_text}")

            step += 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 停止发送数据，正在断开连接...")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
