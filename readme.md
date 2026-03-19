# 配置数据库
在database文件内修改SQLALCHEMY_DATABASE_URL变量即可
例：
```python
SQLALCHEMY_DATABASE_URL = "mysql+aiomysql://root:Cqc114514!@192.168.31.64/Car_data"
```
后端启动后如果数据库中没有表会自动建表
# 开启后端接口
在终端内输入：uvicorn main:app --host 0.0.0.0 --port 8000 --reload

## --host 0.0.0.0
含义：指定服务器监听的 IP 地址。

0.0.0.0 的特殊意义： 这表示“监听所有可用的网络接口”。

如果你不写这行（默认是 127.0.0.1），通常只有你自己这台电脑（Localhost）能访问该网页。

写了 0.0.0.0 后，局域网内的其他设备（比如你的同事、或者你的手机）可以通过你的电脑 IP 地址访问这个服务。这在 Docker 容器中部署时也是必须的。

## --port 8000
含义： 指定服务器监听的端口号。

作用： HTTP 协议默认通常是 80 端口，但开发时为了避免冲突，通常习惯使用 8000、8080 或 5000。这意味着你在浏览器访问时需要输入 http://localhost:8000。

# 开启仿真
重新打开一个终端输入：python simulate.py 