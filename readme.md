# 配置数据库
在database文件内修改SQLALCHEMY_DATABASE_URL变量即可
例：
```python
SQLALCHEMY_DATABASE_URL = "mysql+aiomysql://root:Cqc114514!@192.168.31.64/Car_data"
```
后端启动后如果数据库中没有表会自动建表

## `cars` 表升级
如果数据库里已经有旧版 `cars` 表，需要先手动补 `ip_address`、`work_status` 字段和唯一索引，再启动后端：

```sql
ALTER TABLE cars ADD COLUMN ip_address VARCHAR(45) NULL COMMENT '小车IP地址';
ALTER TABLE cars ADD COLUMN work_status SMALLINT NULL COMMENT '车辆工作状态';
-- 为现有车辆补齐唯一 IP 后，再执行：
ALTER TABLE cars MODIFY COLUMN ip_address VARCHAR(45) NOT NULL COMMENT '小车IP地址';
CREATE UNIQUE INDEX uq_cars_ip_address ON cars (ip_address);
```

## `car_history` 表升级
如果数据库里已经有旧版 `car_history` 表，需要先手动补三个字段再启动后端：

```sql
ALTER TABLE car_history ADD COLUMN yaw FLOAT NULL COMMENT '相对地图原点的朝向(度)';
ALTER TABLE car_history ADD COLUMN mode SMALLINT NULL COMMENT '模式: 1-遥控, 2-自主导航';
ALTER TABLE car_history ADD COLUMN work_status SMALLINT NULL COMMENT '小车工作状态';
```

说明：

- `cars.ip_address` 现在是小车 MQTT 唯一标识
- `longitude` 现在承载地图相对 `x` 坐标
- `latitude` 现在承载地图相对 `y` 坐标
- `gear` 不入库
- `mode`：`1=遥控`，`2=自主导航`
- `cars.status` / `car_history.car_status` 统一采用：
  - `0=待机`
  - `1=充电执行中`
  - `2=任务执行中`
  - `3=任务完成返回中`
  - `4=异常状态`
- `cars.work_status` / `car_history.work_status` 表示车辆工作状态，直接跟随车辆状态 topic 实时更新
- `cars.status` 只会由车辆 MQTT 真实上报更新，任务接口不会直接改写车辆状态
- 车辆状态上报 topic：`car/{car_ip}/status`
- 任务状态上报 topic：`car/{car_ip}/task/report`
- `tasks.status` 由 `task/report` 上报更新，不再从 `work_status` 推导
- 路径下发 topic：`car/{car_ip}/task/path`
- 任务控制命令下发 topic：`car/{car_ip}/task/cmd`

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

# 地图上传说明
地图接口已改为上传 `PGM + YAML` 栅格地图：

- 上传接口：`POST /maps/upload`
- 请求类型：`multipart/form-data`
- 字段：
  - `name`
  - `pgm_file`
  - `yaml_file`

后端会自动：

- 保存原始 `.pgm` 和 `.yaml`
- 解析 YAML 中的 `resolution` 和 `origin`
- 生成一个前端可直接显示的 `preview.png`

静态文件通过 `/static/...` 暴露，地图接口会直接返回 `preview_url`、`pgm_url`、`yaml_url`。
