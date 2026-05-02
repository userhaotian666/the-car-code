# Docker 部署说明

## 1. Docker 是什么

Docker 可以理解为“把后端运行环境一起打包”的工具。

平时直接运行项目时，服务器必须自己装 Python、pip 包、系统依赖，并且版本要刚好匹配。Docker 的做法是：

- 用 `Dockerfile` 描述运行环境，比如 Python 版本、依赖安装、启动命令。
- 根据 `Dockerfile` 构建出一个镜像 `image`。
- 用镜像启动一个容器 `container`，容器里跑的就是后端服务。
- 用 `docker-compose.yml` 把端口、环境变量、文件挂载这些运行参数统一管理。

对应到本项目：

- `Dockerfile`：定义如何打包 FastAPI 后端。
- `requirements.txt`：定义 Python 依赖。
- `.env`：放公司服务器上的数据库、MQTT 等配置。
- `docker-compose.yml`：一条命令启动后端容器。
- `uploads/`：地图上传文件目录，部署时挂载出来做持久化。

## 2. 本项目部署前要确认的信息

先向公司服务器管理员确认这些信息：

- 服务器公网或内网 IP。
- 服务器系统是否已经安装 Docker 和 Docker Compose。
- MySQL 地址、端口、数据库名、用户名、密码。
- 服务器安全组/防火墙是否放行后端端口，默认是 `8000`。
- MQTT broker 地址、端口、账号、密码是否沿用当前配置。

注意：如果 MySQL 是装在宿主服务器上，而后端跑在 Docker 容器里，数据库地址通常不能写 `localhost`。因为容器里的 `localhost` 指的是容器自己，不是宿主机。

## 3. 第一次部署步骤

### 3.1 在服务器安装 Docker

如果服务器是 Ubuntu / Debian，常见安装方式如下：

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo systemctl enable docker
sudo systemctl start docker
docker --version
docker compose version
```

如果公司服务器已经装好 Docker，可以跳过这一步。

### 3.2 把项目传到服务器

方式一：使用 Git。

```bash
git clone <你的仓库地址>
cd my_project
```

方式二：使用 `scp` 上传项目目录。

```bash
scp -r /本机项目路径 用户名@服务器IP:/opt/my_project
ssh 用户名@服务器IP
cd /opt/my_project
```

### 3.3 创建 `.env`

在服务器项目目录里执行：

```bash
cp .env.example .env
nano .env
```

把里面的数据库连接改成真实值：

```env
APP_PORT=8000
SQLALCHEMY_DATABASE_URL=mysql+aiomysql://用户名:密码@数据库服务器IP:3306/Car_data
MQTT_BROKER=broker.emqx.io
MQTT_PORT=1883
MQTT_USER=你的MQTT用户名
MQTT_PW=你的MQTT密码
```

### 3.4 启动后端

```bash
docker compose up -d --build
```

含义：

- `--build`：根据 `Dockerfile` 重新构建镜像。
- `-d`：后台运行容器。

### 3.5 查看运行状态

```bash
docker compose ps
docker compose logs -f backend
```

看到 FastAPI / Uvicorn 正常启动，并且没有数据库表结构报错，就说明容器启动成功。

### 3.6 访问接口

在浏览器访问：

```text
http://服务器IP:8000/
http://服务器IP:8000/docs
```

如果访问不了，优先检查：

- 服务器防火墙或安全组是否放行 `8000`。
- `.env` 里的 `APP_PORT` 是否改过。
- 容器是否启动成功：`docker compose ps`。
- 日志是否报数据库或 MQTT 连接错误：`docker compose logs -f backend`。

## 4. 数据库表结构注意事项

本项目启动时会检查数据库表结构。旧数据库可能需要先执行 `readme.md` 里的升级 SQL。

常见报错包括：

- `cars` 表缺少 `ip_address`。
- `cars.ip_address` 允许为空。
- `cars.ip_address` 缺少唯一索引。
- `car_history` 表缺少 `yaw`、`mode`、`work_status`。
- `maps` 表仍是旧结构。

如果出现这些报错，先按日志提示更新数据库，再重新启动：

```bash
docker compose restart backend
```

## 5. 后续更新部署

每次代码更新后，在服务器项目目录执行：

```bash
git pull
docker compose up -d --build
docker compose logs -f backend
```

## 6. 常用维护命令

停止服务：

```bash
docker compose down
```

重启服务：

```bash
docker compose restart backend
```

查看日志：

```bash
docker compose logs -f backend
```

进入容器：

```bash
docker compose exec backend sh
```

查看容器健康状态：

```bash
docker compose ps
```
