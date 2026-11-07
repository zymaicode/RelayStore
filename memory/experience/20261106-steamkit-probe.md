# 2026-11-06 · SteamKit2 探测工具：代码通了，环境不通

## 事实
- 自建 `tools/steamauth`（SteamKit2 4.0.0-beta.2）实现 appinfo / key / manifest 三种探测。
- CM 45.121.184.22:27017 TCP 可达，但 SteamKit 匿名登录一律 NoConnection（TCP、WebSocket、3.5.0、4.0.0-beta.2 都一样）。
- 同机 steamcmd +login anonymous 正常 → 网络到 Steam 通，差别在客户端握手被拒。

## 结论
- 未拥有 depot 的 key：服务端按 license 拒绝，工具价值只在拿精确 ERESULT。
- 工具保留，换到无限制网络可直接 dotnet run -- key <appid> <depot>。

## 教训
先确认握手成功（logged on: OK）再写探测逻辑；NoConnection 不等于网络不通，先用 steamcmd 做对照实验。
