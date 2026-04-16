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
DEVICE_ID = os.getenv("MQTT_DEVICE_ID", "001")
MQTT_TOPIC = os.getenv("MQTT_TOPIC", f"car/{DEVICE_ID}/status")


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ 成功连接到 MQTT 服务器: {MQTT_BROKER}:{MQTT_PORT}")
    else:
        print(f"❌ 连接失败，返回码: {rc}")


def build_payload(step: int) -> dict:
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
        "msg_id": f"state_{timestamp}_{random.randint(1000, 9999)}",
        "version": "1.0",
        "timestamp": timestamp,
        "device_id": DEVICE_ID,
        "data": {
            "battery": battery,
            "speed": speed,
            "gear": gear,
            "mode": mode,
            "location": {
                "x": x,
                "y": y,
                "yaw": yaw,
            },
        },
    }


def main():
    client = mqtt.Client(client_id=f"Mock_Car_{DEVICE_ID}")
    client.username_pw_set(MQTT_USER, MQTT_PW)
    client.on_connect = on_connect

    print("正在尝试连接 Broker...")
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()

    print("🚗 开始发送模拟状态消息 (按 Ctrl+C 停止)...\n")
    step = 0

    try:
        while True:
            payload = build_payload(step)
            payload_text = json.dumps(payload, ensure_ascii=False)
            client.publish(MQTT_TOPIC, payload_text)
            print(f"[发布] Topic: {MQTT_TOPIC} | Payload: {payload_text}")
            step += 1
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 停止发送数据，正在断开连接...")
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
