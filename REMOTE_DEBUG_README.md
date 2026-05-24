# 后端远程部署与调试说明

## 1. 项目部署方式说明

当前后端项目已经通过 Docker 部署在服务器上。

整体结构可以理解为：

```text
本地电脑
  ↓ SSH 连接
公司/实验室服务器
  ↓ Docker 容器
FastAPI 后端项目
```

后端服务运行在 Docker 容器中，容器名称一般为：

```text
car-backend
```

后端默认端口为：

```text
8000
```

接口访问地址：

```text
http://服务器IP:8000/
http://服务器IP:8000/docs
```

其中 `/docs` 是 FastAPI 自动生成的接口文档页面。

## 2. SSH 连接服务器

在本地电脑终端执行：

```bash
ssh 用户名@服务器IP
```

例如：

```bash
ssh xunlan@192.168.0.154
```

如果 SSH 端口不是默认的 `22`，需要加 `-p`：

```bash
ssh -p 端口号 用户名@服务器IP
```

例如：

```bash
ssh -p 2222 xunlan@192.168.0.154
```

如果连接成功，会提示输入密码：

```text
xunlan@192.168.0.154's password:
```

输入密码时终端不会显示任何字符，这是正常现象，输入完成后按回车即可。

## 3. 如果 SSH 没反应怎么排查

### 3.1 检查网络是否能连通

在本地电脑执行：

```bash
ping 服务器IP
```

例如：

```bash
ping 192.168.0.154
```

如果没有响应，可能原因包括：

```text
本地电脑和服务器不在同一个局域网
服务器 IP 写错
服务器没有联网
需要连接公司/校园 VPN
```

### 3.2 检查 SSH 端口是否开放

在本地电脑执行：

```bash
nc -vz 服务器IP 22
```

例如：

```bash
nc -vz 192.168.0.154 22
```

如果成功，会看到类似：

```text
Connection to 192.168.0.154 port 22 succeeded
```

如果失败，说明服务器 SSH 服务没有开启，或者防火墙阻止了 22 端口。

### 3.3 在服务器上检查 SSH 服务

如果可以直接操作服务器，在服务器上执行：

```bash
sudo systemctl status ssh
```

如果 SSH 没安装：

```bash
sudo apt update
sudo apt install -y openssh-server
sudo systemctl enable ssh
sudo systemctl start ssh
```

检查 22 端口：

```bash
ss -lntp | grep :22
```

### 3.4 检查防火墙

```bash
sudo ufw status
```

如果防火墙开启，需要放行 SSH：

```bash
sudo ufw allow 22
```

## 4. 进入项目目录

SSH 登录服务器后，进入项目目录：

```bash
cd ~/xht/the-car-code
```

可以用下面命令确认当前目录：

```bash
pwd
ls
```

正常应该能看到：

```text
Dockerfile
docker-compose.yml
.env
main.py
requirements.txt
```

## 5. 查看后端是否正在运行

### 5.1 使用 docker-compose 查看

```bash
docker-compose ps
```

如果看到类似：

```text
car-backend   Up
```

说明后端正在运行。

### 5.2 使用 docker 查看

```bash
docker ps
```

如果列表里有：

```text
car-backend
```

并且状态是 `Up`，说明容器正在运行。

## 6. 启动后端

在项目目录下执行：

```bash
docker-compose up -d --build
```

含义：

```text
up        启动服务
-d        后台运行
--build   重新构建镜像
```

通常在以下情况使用：

```text
第一次部署项目
修改了代码
修改了 requirements.txt
修改了 Dockerfile
执行 git pull 更新代码后
```

## 7. 停止后端

```bash
docker-compose down
```

这个命令会停止并删除当前 compose 创建的容器。

注意：项目中的 `uploads` 目录已经挂载到服务器本地，一般不会因为容器删除而丢失上传文件。

## 8. 重启后端

如果只是修改了 `.env` 或者想重启服务：

```bash
docker-compose restart backend
```

也可以直接重启容器：

```bash
docker restart car-backend
```

## 9. 查看后端实时日志

这是远程调试最常用的命令：

```bash
docker-compose logs -f backend
```

或者：

```bash
docker logs -f car-backend
```

访问接口时，终端会出现类似：

```text
INFO:     192.168.0.10:53210 - "GET / HTTP/1.1" 200 OK
INFO:     192.168.0.10:53212 - "GET /docs HTTP/1.1" 200 OK
INFO:     192.168.0.10:53218 - "POST /maps/upload HTTP/1.1" 200 OK
```

其中：

```text
GET /docs                  表示访问接口文档
POST /maps/upload          表示调用上传地图接口
200 OK                     表示请求成功
404 Not Found              表示接口不存在
500 Internal Server Error  表示后端代码报错
```

退出日志查看：

```text
Ctrl + C
```

注意：`Ctrl + C` 只是退出日志查看，不会停止后端容器。

## 10. 查看最近日志

只查看最近 100 行：

```bash
docker logs --tail 100 car-backend
```

查看最近 100 行并持续追踪：

```bash
docker logs -f --tail 100 car-backend
```

## 11. 测试后端接口是否正常

在服务器上执行：

```bash
curl http://127.0.0.1:8000/
```

正常会返回类似：

```json
{"message":"Server is running in async mode with Scheduler and MQTT!"}
```

测试接口文档：

```bash
curl -I http://127.0.0.1:8000/docs
```

如果看到：

```text
HTTP/1.1 200 OK
```

说明接口文档可以访问。

## 12. 在浏览器访问后端

如果服务器防火墙已经放行 8000 端口，可以在本地浏览器访问：

```text
http://服务器IP:8000/
http://服务器IP:8000/docs
```

例如：

```text
http://192.168.0.154:8000/docs
```

如果访问不了，需要检查：

```text
服务器 IP 是否正确
后端容器是否运行
8000 端口是否放行
本地电脑和服务器是否在同一网络
```

检查服务器端口：

```bash
ss -lntp | grep 8000
```

## 13. 使用 SSH 隧道访问后端

如果服务器没有开放 8000 端口，可以使用 SSH 端口转发。

在本地电脑执行：

```bash
ssh -L 8000:127.0.0.1:8000 用户名@服务器IP
```

例如：

```bash
ssh -L 8000:127.0.0.1:8000 xunlan@192.168.0.154
```

保持这个 SSH 连接不要关闭。

然后在本地浏览器访问：

```text
http://127.0.0.1:8000/docs
```

此时本地访问的实际上是远程服务器上的后端服务。

## 14. 更新后端代码

如果项目代码是通过 Git 管理的，更新流程如下：

```bash
cd ~/xht/the-car-code
git pull
docker-compose up -d --build
docker-compose logs -f backend
```

如果代码更新后启动失败，查看日志：

```bash
docker-compose logs -f backend
```

## 15. 修改环境变量

环境变量文件是：

```text
.env
```

编辑：

```bash
nano .env
```

常见内容：

```env
APP_PORT=8000
SQLALCHEMY_DATABASE_URL=mysql+aiomysql://root:密码@数据库IP:3306/Car_data
MQTT_BROKER=broker.emqx.io
MQTT_PORT=1883
MQTT_USER=用户名
MQTT_PW=密码
```

保存 nano：

```text
Ctrl + O
回车
Ctrl + X
```

修改 `.env` 后重启后端：

```bash
docker-compose restart backend
```

## 16. 进入容器内部调试

进入后端容器：

```bash
docker exec -it car-backend sh
```

进入后可以执行：

```bash
pwd
ls
python --version
python -c "import fastapi; print(fastapi.__version__)"
```

退出容器：

```bash
exit
```

注意：容器内修改文件通常不推荐，因为容器重建后修改可能丢失。建议在服务器项目目录修改源码，然后重新构建。

## 17. 常见问题

### 17.1 docker-compose 命令不存在

如果执行：

```bash
docker-compose version
```

提示找不到命令，需要安装：

```bash
sudo apt update
sudo apt install -y docker-compose
```

### 17.2 docker compose 命令不存在

有些服务器没有新版 Compose V2，只能使用老版命令：

```bash
docker-compose
```

如果已经安装的是老版，就使用：

```bash
docker-compose up -d --build
```

而不是：

```bash
docker compose up -d --build
```

### 17.3 数据库连接失败

查看日志：

```bash
docker-compose logs -f backend
```

常见错误：

```text
Can't connect to MySQL server
```

表示数据库地址或端口不通。

```text
Access denied for user
```

表示数据库用户名或密码错误。

```text
Unknown database 'Car_data'
```

表示数据库不存在，需要创建：

```sql
CREATE DATABASE Car_data CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 17.4 端口被占用

如果 8000 被占用，可以修改 `.env`：

```env
APP_PORT=8001
```

然后重新启动：

```bash
docker-compose up -d --build
```

访问地址变成：

```text
http://服务器IP:8001/docs
```

## 18. 最常用命令汇总

进入服务器：

```bash
ssh xunlan@192.168.0.154
```

进入项目：

```bash
cd ~/xht/the-car-code
```

启动后端：

```bash
docker-compose up -d --build
```

查看状态：

```bash
docker-compose ps
```

查看日志：

```bash
docker-compose logs -f backend
```

重启后端：

```bash
docker-compose restart backend
```

停止后端：

```bash
docker-compose down
```

进入容器：

```bash
docker exec -it car-backend sh
```

测试接口：

```bash
curl http://127.0.0.1:8000/
```

浏览器访问：

```text
http://服务器IP:8000/docs
```
