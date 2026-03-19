import paho.mqtt.client as mqtt
import time
import json
import random
import math

# --- 配置参数 ---
BROKER_ADDRESS = "broker.emqx.io" 
BROKER_PORT = 1883
TOPIC_LOCATION = "fire_car/device_001/location" 

# --- 连接回调函数 (1.x 版本，4个参数) ---
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"✅ 成功连接到 MQTT 服务器: {BROKER_ADDRESS}")
    else:
        print(f"❌ 连接失败，返回码: {rc}")

def main():
    # 1. 初始化客户端 (1.x 版本写法，直接用 client_id 关键字赋值避免警告)
    client = mqtt.Client(client_id="Mock_Fire_Car_001")  
    client.on_connect = on_connect

    # 2. 连接服务器并启动网络循环
    print("正在尝试连接 Broker...")
    client.connect(BROKER_ADDRESS, BROKER_PORT, 60)
    client.loop_start() 

    print("🚗 开始发送模拟小车数据 (按 Ctrl+C 停止)...\n")
    
    current_x = 0.0
    current_y = 0.0
    angle = 0.0

    try:
        while True:
            # 模拟小车运动
            current_x = 5.0 * math.cos(angle) + random.uniform(-0.1, 0.1)
            current_y = 5.0 * math.sin(angle) + random.uniform(-0.1, 0.1)
            angle += 0.2
            
            battery = random.randint(85, 100)
            status = "0" if random.random() > 0.95 else "1"

            payload = {
                "device_id": "2",
                "x": round(current_x, 3), 
                "y": round(current_y, 3), 
                "battery": battery,
                "status": status,
                "timestamp": int(time.time())
            }
            
            payload_str = json.dumps(payload)
            
            # 3. 发布消息
            client.publish(TOPIC_LOCATION, payload_str)
            print(f"[发布] Topic: {TOPIC_LOCATION} | Payload: {payload_str}")
            
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n🛑 停止发送数据，正在断开连接...")
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()