# 🎸 Stems Pro

> 智能多轨分离系统 — 上传一首歌，自动分离为 6 个独立音轨，多轨同步播放，支持静音/独奏/节拍器。

## 运行方案

**5 种方案，从零成本到最省心：**

| # | 方案 | GPU 在哪 | 需要云服务器 | 月费 | 异地可用 | 适合场景 |
|---|------|---------|-------------|------|---------|---------|
| ① | 云服务器 + ROG GPU | 家中电脑 | ✅ 2核6G | ~$5 | ✅ | 最省心，家里电脑开机即忘 |
| ② | 云服务器 + Colab | Colab T4 | ✅ 2核6G | ~$5 | ✅ | 没有 NVIDIA 显卡也能用 |
| ③ | Tailscale 直连 | 家中电脑 | ❌ | 0 | ✅ | 有 GPU 电脑，不想花一分钱 |
| ④ | Cloudflare Tunnel | 家中电脑 | ❌ | 0 | ✅ | 学校/公司网极端封锁时的兜底 |
| ⑤ | 纯离线 | 家中电脑 | ❌ | 0 | ❌ | 不联网也行，U 盘拷 |

**方案 ③④ 的代码已写好**：`local/local_server.py` 一把梭，`python local_server.py` 启动即用。

```
        ┌──── 平板 App ─────────────────────────────┐
        │  选择 .ncm → 上传 → 等分离 → 下载分轨 → 播放  │
        └──────────────────┬─────────────────────────┘
                           │
        ┌──────────────────┴─────────────────────────┐
        │  方案①/②: 云服务器中转                       │
        │  方案③: Tailscale P2P 直连                  │
        │  方案④: Cloudflare HTTPS 隧道               │
        │  方案⑤: U 盘 / 局域网共享                    │
        └──────────────────┬─────────────────────────┘
                           │
                    ┌──────┴──────┐
                    │  GPU 分离   │
                    │  Demucs v4  │
                    │  6 轨 MP3    │
                    └─────────────┘
```

## 技术栈

| 层 | 技术 |
|---|------|
| AI 分离 | Demucs v4 (htdemucs_6s) |
| GPU 算力 | Google Colab (T4) / 本地 NVIDIA GPU |
| 服务器 | FastAPI + SQLite (云版) / Flask (无服务器版) |
| Android App | Kotlin + Jetpack Compose + MediaCodec |
| NCM 解密 | 纯 Python 实现 (pycryptodome) |
| BPM 检测 | librosa (HPSS + onset + 八度纠错) |

## 项目结构

```
stems-pro/
├── colab/
│   ├── stems_pro.py                    # Colab 4-Cell 批量处理
│   └── Stems_Pro_GPU_Separation.ipynb
├── local/
│   ├── local_processor.py              # Windows 本地 GPU 处理器 (ROG)
│   ├── local_server.py                 # Flask 迷你服务 (方案③④用)
│   ├── run.bat                         # 一键启动
│   └── setup.bat                       # 环境安装
├── server/
│   ├── fix_server_final.py             # 服务器一键部署脚本 (方案①②)
│   ├── run.py                          # FastAPI 入口
│   ├── stems.service                   # systemd 配置
│   └── app/
│       ├── main.py                     # API 路由
│       ├── models.py                   # ORM 模型
│       ├── database.py                 # SQLite 连接
│       ├── schemas.py                  # Pydantic 校验
│       ├── admin.py                    # 管理后台
│       └── templates/admin.html
└── android/StemsPro/                   # Android App (Kotlin/Compose)
    └── app/src/main/java/com/stemspro/app/
        ├── player/
        │   ├── MultiTrackPlayer.kt     # 混音引擎 (预解码+phase-counter节拍器)
        │   └── AudioDecoder.kt         # MediaCodec → PCM ShortArray
        ├── data/
        │   ├── api/StemsApi.kt         # Retrofit 接口
        │   ├── repository/             # 数据层
        │   └── local/AppDatabase.kt    # Room 缓存
        ├── ui/screens/
        │   ├── LibraryScreen.kt        # 歌曲列表
        │   ├── PlayerScreen.kt         # 播放器 (BPM长按加减)
        │   └── UploadScreen.kt         # 上传
        └── di/AppContainer.kt          # 手动 DI
```

## 各方案部署

### 方案① 云服务器 + ROG GPU

**服务器部署：**
```bash
# 把 server/fix_server_final.py 上传到 /tmp/
python3 /tmp/fix_server_final.py && systemctl restart stems
```

**家中 GPU 电脑：**
```bash
setup.bat              # 装依赖 (一次)
run.bat                # 一次性处理所有 pending
run.bat --watch         # 持续蹲守，有歌自动处理
```

### 方案② 云服务器 + Colab

服务器同上。Colab：打开 `colab/stems_pro.py`，复制 4 个 CELL 到 Colab (Runtime → T4 GPU)，Run all。

### 方案③ Tailscale 直连 (无服务器)

```
家 (GPU电脑)                       教室 (平板)
     │                                  │
     └──── Tailscale P2P ─── 互联网 ────┘
                     │
          虚拟 IP: 100.x.x.x
          就像在同一局域网
```

1. 注册 [Tailscale](https://tailscale.com)（免费 3 用户），GPU 电脑和平板各装客户端，登录同一账号
2. 家中 GPU 电脑开启 Flask 服务：
   ```bash
   pip install flask
   python local/local_server.py --host 0.0.0.0 --port 5000
   ```
3. App 服务器地址改为 Tailscale 虚拟 IP，如 `http://100.64.32.17:5000`

Tailscale 优先走 P2P 直连（延迟低、不过第三方）。如果学校封了 UDP，自动降级 DERP 中继。

### 方案④ Cloudflare Tunnel (网络极端封锁兜底)

```bash
winget install cloudflare.cloudflared
cloudflared tunnel --url http://localhost:5000
# 输出: https://stems-pro-try.trycloudflare.com
```

平板访问这个域名即可。走 HTTPS 443，任何网络下都不可能被封。每次重启 URL 会变。

### 方案⑤ 纯离线

GPU 电脑跑 `local_processor.py` 处理 `.ncm` 文件，分轨拷 U 盘/共享文件夹，平板本地播放。

## API

所有方案共用同一套 API（REST JSON）：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/songs` | 歌曲列表 |
| GET | `/api/songs/pending` | 待处理 |
| POST | `/api/songs` | 创建歌曲 |
| DELETE | `/api/songs/{id}` | 删除 |
| POST | `/api/songs/{id}/tracks` | 上传分轨 |
| POST | `/api/songs/{id}/original` | 上传原始文件 |
| GET | `/api/songs/{id}/original/download` | 下载原始文件 |
| GET | `/api/songs/{id}/download` | ZIP 打包下载 |
| GET | `/api/tracks/{id}/download` | 单轨下载 |
| POST | `/api/songs/{id}/status` | 更新状态+BPM |
| GET | `/api/stats` | 服务器统计 |

## 关键技术难点与解决方案

### 1. NCM 文件解密 (AES 密钥错误)

**问题**：NCM 解密失败，AES-ECB 解密后找不到 `neteasecloudmusic` 标志。

**根因**：项目早期使用的 AES 密钥是错的——`687A4852416D626F526E68394D41454B4B`，正确的是 `687A4852416D736F356B496E62617857`。两串 hex 看起来相似但完全不同。

**解决**：从社区逆向分析的项目 (ncmdump) 找到正确的 CORE_KEY 和 META_KEY。NCM 文件结构为：`CTENFDAM(8) + gap(2) + key_len(4) + key_data + metadata + image + RC4-encrypted audio`。密钥先 XOR 0x64，再 AES-ECB 解密，取 `neteasecloudmusic` 后 17 字节作为 RC4 key。

### 2. Android 播放无声

**问题**：下载完点击播放完全没声音，UI 显示播放中但进度条不动。

**根因**：`play()` 开头调用了 `stop()`，而 `stop()` 会执行 `paths.clear()`。刚通过 `loadPaths()` 加载的 6 个文件路径瞬间被清空。

**解决**：`play()` 不再调用 `stop()`，改为手动清理旧的 `playJob` 和 `AudioTrack`，保留 `paths` 不变。通过 `wasStopped` 标志决定是否重置 `currentFrame`。

### 3. 卡顿 — 6×MediaCodec 同时实时解码

**问题**：播放中途出现间歇性卡顿，尤其在金属等密集音乐时明显。

**根因**：`streamMix()` 循环里开了 6 个 `MediaCodec` 实例实时解码。每轮 4096 样本需要 6 次 `dequeueOutputBuffer()` 阻塞等待，6 个解码器竞争硬件资源，累积延迟 > 缓冲区时长。

**尝试的方案**：
- 增大缓冲区 (4096→8192→32768)：32768 时总缓冲 1.5 秒，但 6 个 `MediaCodec` 同时解码的瞬时 CPU 峰值仍然导致掉帧
- 改用 ArrayDeque 环形缓冲：减少了分配开销，但解码器调度延迟才是瓶颈

**最终方案 — 预解码到内存**：`AudioDecoder.decode()` 串行解码（一次一个 `MediaCodec`），存入 `ShortArray`，播放时纯数组读取无任何解码调用。BASS Audio Library 和 Android SoundPool 官方文档均推荐此方案。6 轨约 120MB，现代手机完全足够。

### 4. 音轨音量偏低

**问题**：6 轨混音后总音量显著低于原曲。

**根因**：
- 下混时 `(L+R)/2` → -6dB
- 混音时 `mixBuf[i] / active` 除以 6 → -15dB
- Demucs 默认 `--clip-mode rescale` 会独立压低每轨

**解决**：
- 下混：`L+R` 不除 2
- 混音：直接求和 + `coerceIn` 硬夹保护
- 分离参数：`--clip-mode clamp`

### 5. NCM 文件上传与时序竞争

**问题**：ROG watch 模式检测到新歌立即开始下载分离，但平板 App 的 `.ncm` 文件还在上传中。

**解决**：ROG processor 的 watch 循环增加判断——不仅检查 `status == "pending"`，还要验证 `original_file is not None`。

### 6. MediaCodec INFO_OUTPUT_FORMAT_CHANGED 卡死

**问题**：`MediaCodec` 解码 MP3 时偶尔卡在死循环。

**根因**：`dequeueOutputBuffer()` 返回 `INFO_OUTPUT_FORMAT_CHANGED (-2)` 时，代码未处理该返回值。

**解决**：`when` 分支完整处理所有可能的 `outIdx` 值。

### 7. 节拍器无声 + 无重音区分

**问题**：节拍器开关打开但听不到 click 声；启用重音后所有拍子声音一样。

**根因**：click 样本写入整个小节数组但只填了第 0 拍；`prebuildMetronome()` 只生成一种 click（if-else），注入时所有拍子同一个音。

**解决**：拆为 `metroClickAccent`（1800Hz）和 `metroClickSamples`（1200Hz）两个独立数组，每次两个都生成。注入时根据 `beatIdx % 4 == 0` 选择重音。

### 8. 节拍器跑音/漂移

**问题**：节拍器 click 跟音乐对不上，越播越偏，seek 后完全错乱。

**根因**：节拍位置用绝对帧位置计算 `beatIdx = gf / metroBeatLen`。这个公式把节拍网格锚定在音频文件第 0 帧处，`metroBeatLen` 是整数，累积误差会越播越大。seek 后 `gf` 跳到新位置，beatIdx 不一定是整数倍的 beat 边界，click 直接错位。

**解决**：改用相位计数器（phase counter）：
```
每帧 metroPhase++
到达 metroBeatLen 后: metroPhase=0, metroBeatIdx=(beatIdx+1)%4
click 在 metroPhase < clickLen 时注入，相位 0 正好落在节拍起点
seek/stop 时: metroPhase=0, metroBeatIdx=0
BPM 变化时: if (metroPhase >= metroBeatLen) { reset }
```
好处：
- **无累积误差**：每 beat 严格 `metroBeatLen` 帧，整数截断只影响最后一个 beat 尾（< 1 帧误差，不可闻）
- **seek 后立即对齐**：相位归零，下一个 beat 从 seek 位置开始
- **sample-accurate**：click 注入和音频数据走同一块 buffer → 同一帧 → 同一 write()，跟音乐严格同步

### 9. Android 下载路径权限问题

**问题**：旧版存 `/sdcard/Music/StemsPro/`，部分设备静默失败。

**解决**：改用 app 内部存储 `context.filesDir/tracks/{songId}/`，无需权限，卸载自动清理。

## App 功能

- 🎧 6轨同步播放（预解码 + 纯内存混音）
- 🔊 每轨独立音量滑块
- 🔇 Mute 静音 / 🎸 Solo 独奏
- 🥁 节拍器（开关 + 音量 + 重音 + sample-accurate 相位同步）
- ⏱️ BPM 显示 + 滑块 + 长按 ± 持续调节（加速衰退）
- 📥 一键下载分轨 ZIP
- 📤 上传歌曲（支持 .ncm 网易云格式自动解密）
- 🗑️ 删除歌曲

## 许可

MIT
