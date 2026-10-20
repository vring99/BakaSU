# BakaSU Pro 私有构建

基于 BakaSU 35229，基础提交为 `d7260ca1e5c128061122924d0d48754e361e135c`。
应用名称为 **BakaSU Pro**。安装包名可以每次指定，留空时每次生成新的随机包名。
Gradle 和 ksud 使用同一次构建选定的包名。内核依靠证书识别管理器，不依赖包名。
管理器自检从同一份 `kernel/manager/manager_sign.h` 生成证书配置，避免私有签名被误报。
内核版本信息中已有的 `@` 署名统一替换为 `@BakaSUPro`，前面的版本号和提交信息保留。
该规则同时用于 GKI 和 LKM；原本没有 `@` 后缀的自定义格式保持不变。

## 首次 push 与 GitHub 编译

已确认自有仓库为 `https://github.com/vring99/BakaSU`。
本地 `origin` 指向此仓库，官方仓库保留为 `upstream`。
私有版本使用基于 35229 的 `codex/bakasu-pro-latest` 分支。
后续修改完成后，可执行：

```powershell
git add .
git commit -m "Prepare BakaSU Pro private manager and GitHub builds"
git push -u origin codex/bakasu-pro-latest
```

你的远端 `main` 已有上游提交；此处将私有版本推送为独立分支。
推送后，在 GitHub 仓库设置中将默认分支切换为 `codex/bakasu-pro-latest`，
GitHub 才会显示此分支新增工作流的手动运行按钮。

配置签名只需做一次。安装并登录 GitHub CLI（`gh auth login`），设置 JDK 21 的 `JAVA_HOME`，
在仓库根目录运行：

```powershell
python scripts/private_manager.py github-secrets --repo vring99/BakaSU
```

此命令会读取本地签名配置，先导出证书核对内核白名单，再将下面四个 Secrets 写入指定仓库。
密钥和密码通过标准输入传给 `gh`，不会输出其内容。没有 GitHub CLI 时，也可以按下表手动添加。

随后打开 **Actions → Build BakaSU Pro → Run workflow**：

1. `package_name` 填写自定包名，或留空生成随机包名。
2. 等待工作流结束。
3. 下载 **BakaSU-Pro-release**，其中包含完整 APK、SHA-256、包名、公开证书和 GKI 补丁。

普通 push 不触发旧的管理器打包；`build-manager.yml` 作为兼容入口调用同一私有构建流程。
上游的代码检查工作流仍可在 push / PR 后执行。
需要发布 GitHub Release 时，使用 **Release BakaSU Pro** 并填写 `tag_name`；推送 `v*` 标签也会发布。

## 签名与 GKI / LKM

`kernel/manager/manager_sign.h` 中的公开证书信息同时用于 GKI 内置和 LKM 模式：

- DER 长度：826 字节（`0x033a`）。
- SHA-256：`4467a1d3c7ca99f505643f8a60ef5d98ebb08cc6bf043c82be4f668ffc737e0b`。
- `apk_sign.c` 的编译期白名单仅保留此证书；下游误开多管理器支持也不会加入官方/KOWSU 签名。
- 默认关闭 `CONFIG_KSU_MULTI_MANAGER_SUPPORT`，DDK 的 arm64/x86_64 路径也显式关闭。
- 保留用户主动配置的动态管理器功能；这里关闭的是其他管理器的自动互认。
- APK 使用 v2 签名，关闭 v1/v3/v4，符合内核解析要求。

本地签名文件存放在 `manager/private-signing/`（Git 已忽略）：

```text
bakasu-custom.jks
signing.properties
manager-cert.der
```

保存并备份该目录。更新管理器继续使用同一私钥；随机包名不同会形成另一个应用，
需要覆盖更新时填写前一次的包名。私钥、密码及其 Base64 内容均不应提交 Git。

## 可选：本地管理器构建

设置 JDK 21 的 `JAVA_HOME` 和 Android SDK 的 `ANDROID_SDK_ROOT`，然后在仓库根目录运行：

```powershell
# 留空：本次生成随机包名
python scripts/private_manager.py build

# 指定包名
python scripts/private_manager.py build --name com.example.bakasupro
```

脚本从本地 `signing.properties` 读取私钥配置，通过环境变量传递签名密码，执行
`spotlessCheck`、`testDebugUnitTest`、`assembleRelease`、`lintRelease`，并核对 APK 的真实包名、名称和签名。
`manager/app/build/outputs/apk/release/private-build.json` 记录本次包名、证书和文件 SHA-256。

此阶段的 Gradle APK **尚未注入 ksud/LKM**；安装用的完整 APK 由下面的 Actions 流程打包。

## Actions 签名与产物

自有仓库需要以下四个 Actions Secrets（可使用上面的命令配置）：

| Secret | 本地来源 |
| --- | --- |
| `KEYSTORE` | `bakasu-custom.jks` 文件的 Base64 |
| `KEYSTORE_PASSWORD` | `signing.properties` 同名字段 |
| `KEY_ALIAS` | `signing.properties` 同名字段 |
| `KEY_PASSWORD` | `signing.properties` 同名字段 |

手动运行 **Build BakaSU Pro**，输入 `package_name`，或留空生成随机包名。
工作流先校验证书，再编译全部既有 arm64/x86_64 KMI 的 LKM、ksuinit、四架构 ksud 和管理器，
最后注入 ksud 并重新签名，逐个核对最终 APK。该入口只生成构建产物。

- `BakaSU-Pro-release`：完整 APK、SHA256SUMS.txt、本次包名、公开证书和 GKI 补丁。
- `BakaSU-Pro-identity`：公开证书、本次包名、GKI 源码补丁。
- 各 `*-lkm`：使用同一自有证书的 LKM 文件。

签名 secrets 不完整或与内核证书不一致时，流程立即失败，不使用调试签名代替。

## 接入 GKI 内核编译

本仓库的 Actions 编译管理器和 LKM；GKI 的完整内核镜像继续由你的 GKI 内核仓库编译。
推荐直接使用本分支的 kernel 源码，签名及下文的 SUSFS 适配均已内置，不需要额外补丁。
仅为兼容仍使用官方 **35229** 的外部构建，Actions 保留导出
`gki-manager-signature.patch`，包含签名、信息查询权限和原生 SUSFS 适配所需文件。
仓库内的旧副本 `docs/patches/gki-manager-signature-35229.patch` 只包含原有签名改动，
不代表当前原生 SUSFS 接入代码；两者不能混用。
应在 BakaSU 源码拉取后、真正编译前应用（命令在 BakaSU 源码根目录运行）：

```bash
git apply --check /path/to/gki-manager-signature.patch
git apply /path/to/gki-manager-signature.patch
```

如果使用本分支源码，直接使用已有的私有认证代码，不要重复应用补丁。
本分支的 `kernel/setup.sh` 默认拉取 `vring99/BakaSU` 的
`codex/bakasu-pro-latest` 分支。已有 `KernelSU` 目录不会自动替换远程仓库，
接入时应确认实际 checkout 来自本分支，不能继续使用工作流中固定的官方提交。
编译配置保持：

```text
CONFIG_KSU=y
CONFIG_KSU_MULTI_MANAGER_SUPPORT=n
```

### GKI + SUSFS 原生接入

本分支统一编译 `kernel/feature/selinux_hide.c`，SUSFS 和 Tracepoint 共用已有的
SID 表同步和查询时序修复。旧的 `selinux_hide_susfs.c` 已移除，不需要在构建时下载
KernelSU 的 `selinux_hide.c`、覆盖文件或删除 `Please wait susfs update` 阻断。
Linux 内核本身仍须集成 SUSFS 官方的内核补丁，并启用 `CONFIG_KSU_SUSFS=y`。
不要再向本分支应用官方 KernelSU 的 `10_enable_susfs_for_ksu.patch`。

当前接入要求 SUSFS 官方 2026-10-19 的“Reuse upstream selinux_hide existing code”
更新或包含相同接口的后续版本。官方内核补丁保持原样，由 SUSFS 的内联入口调用
本分支导出的 KSU 函数：

| 内核 | SUSFS SELinux 接口 |
| --- | --- |
| Android 12 / 5.10 至 Android 16 / 6.12 | `my_setprocattr`、`my_write_context`、`my_write_access` |

编译前会检查这些接口是否已接入；旧版或缺失的接口会给出具体错误，不能仅删除检查。
这部分仅支持内置 `CONFIG_KSU=y`，LKM 继续使用原有 Tracepoint 实现。
SUSFS 模式由官方内核补丁选择调用入口，不再重复修改 SELinux 函数表。
新版官方 SUSFS 还会调用 `ksu_setup_preinit_file` 和
`ksu_preinit_handle_post_execveat`。Pro 已移植官方 KernelSU 的完整 preinit runner
（`0faec0cc`，并包含 `e9ef3540` 的 Linux 6.19+ 兼容修复）。SUSFS 内置模式由官方
补丁调用这两个接口，Tracepoint 模式从原有 execve 入口接入；正常启动的 GKI 和
LKM 均可使用，要求 SUSFS 或 Tracepoint Hook；手动 Hook 和系统启动后才加载的
late-load 模式不支持。
runner 在 PID 1 执行 `/system/bin/init selinux_setup` 时运行模块的
`preinit/preinit.conf`，完成后执行原来的 init；无法启动 runner 时回退原启动路径。
构建依赖目标内核安装的 UAPI 头文件（`$(objtree)/usr/include`），缺失时按官方机制
禁用 runner；此时 `compat/susfs_preinit.c` 仅保留“不支持”接口以避免链接失败。
模块同步、失败启动计数、空间限制和恢复命令见 [PREINIT.md](PREINIT.md)。
源码及接口检查不代表全部内核版本已完成真实编译或真机验证。

LKM 流程对应 `CONFIG_KSU=m`，证书校验代码相同。不设置固定 `KSU_MANAGER_PACKAGE`，
否则新随机包名可能被包名过滤提前拒绝。

只安装本管理器而未重编 GKI/LKM，不会改变设备上旧内核接受的管理器签名。
源码检查、管理器构建均不代替真实 GKI/LKM 编译、刷入和设备验证。

### 驱动入口与信息查询权限

申请普通驱动 fd，以及 `GET_INFO`、`GET_INFO_LEGACY`、`GET_FULL_VERSION`、
`CHECK_SAFEMODE` 四条查询，统一要求调用者属于以下任一情况：

- 内核已登记的管理器（正常安装路径校验 Pro 私有证书）。
- 当前 UID 为 0，包括启动阶段和 ksud 的 root 调用。
- 当前 UID 具有有效 su 授权。

未授权 shell 和其他未授权进程无法通过上述入口申请 fd。即使持有以前取得、继承或
收到的 fd，四条查询也会重新检查当前身份；撤销授权后，后续查询返回 `EPERM`。
这不撤回已经读出的信息，也不会终止已经获得 root 的进程。

调试编译不再默认放行 shell。管理员显式设置的 `allow_shell=1` 仍然有效；
该参数会独立于管理器的普通授权名单放行 UID 2000，包括 su 授权。因此使用该参数时，
仅在管理器中撤销 shell 授权不足以阻止 shell，需要取消启动/模块参数并重新加载或重启。

root 配置的动态管理器，以及启用 Toolkit/Debug 后由管理员登记的管理器，仍属于
内核认可的管理器；它们不是未知 APK 自动通过证书验证。管理器身份按 appId 判断，
同一 appId 的其他 Android 用户实例也会被认可。

su 会话 fd 仅保留原有的 `GET_WRAPPER_FD`、`DISABLE_ESCAPE_TO_ROOT` 两条特殊许可，
不额外放行上述四条查询或授予管理权限。原有配置、授权名单等命令继续使用各自的
管理器/root 权限检查。

限制同时用于本分支的 GKI/LKM 源码和导出的 GKI 补丁；更新管理器 APK 本身不会改变
旧内核行为。主机回归测试执行真实权限函数、命令表和入口函数，模拟内核身份及底层操作，
不能替代重编内核和刷入后的真机验证，也不保证屏蔽其他检测途径。

修改上述内核认证文件后，在本仓库重新生成补丁：

```powershell
python scripts/private_manager.py gki-patch --output docs/patches/gki-manager-signature-35229.patch
```
