"""MQTT 测试兼容入口。

这个文件本身不承载业务逻辑，只是为了兼容旧引用路径：
- 路径下发测试逻辑已经拆到 `publisher.py`
- 接收处理逻辑已经拆到 `receiver.py`

如果其他地方还在 `from MQTT.test import ...`，
这里可以继续把它们转发到新模块，避免老代码立刻失效。
"""

from .publisher import _build_path_publish_payload, publish_path_to_car
from .receiver import process_car_data, mqtt_listener
