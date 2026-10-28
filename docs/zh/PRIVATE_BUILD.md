# BakaSU Pro 私有构建

运行时代码对齐 BakaSU 35252，基础提交为 `d5e9e025b8b49155f8014684d64c91742b465f65`。
保留私有身份、更新源、权限收紧和 Magica/外部入口移除；其余运行时代码恢复官方基准。
APK 版本号仍按 Pro 分支提交数递增，不降为 35252，以支持覆盖更新。
应用名称为 **BakaSU Pro**。安装包名可以每次指定，留空时每次生成新的随机包名。
Gradle 和 ksud 使用同一次构建选定的包名。内核依靠证书识别管理器，不依赖包名。
管理器自检从同一份 `kernel/manager/manager_sign.h` 生成证书配置，避免私有签名被误报。
内核版本信息中已有的 `@` 署名统一替换为 `@BakaSUPro`，前面的版本号和提交信息保留。
该规则同时用于 GKI 和 LKM；原本没有 `@` 后缀的自定义格式保持不变。

## 首次 push 与 GitHub 编译

已确认自有仓库为 `https://github.com/vring99/BakaSU`。
本地 `origin` 指向此仓库，官方仓库保留为 `upstream`。
当前私有版本使用 `codex/build-35233` 分支。
后续修改完成后，可执行：

```powershell
# 仅暂存本次修改，不要包含 diagnostics 或签名私钥
git add <本次修改的文件>
git commit -m "Prepare BakaSU Pro private manager and GitHub builds"
git push -u origin codex/build-35233
```

你的远端 `main` 已有上游提交；此处将私有版本推送为独立分支。
推送后，在 GitHub 仓库设置中将默认分支切换为 `codex/build-35233`，
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
`spotlessCheck`、`testDebugUnitTest`、`lintRelease`，通过后单独执行官方形式的
`assembleRelease -Pcommit=<HEAD> -PKSU_PACKAGE_NAME=<包名> -PKSU_NAME="BakaSU Pro"`，
并核对 APK 的真实包名、名称和签名。保留官方 Gradle/R8/CMake 配置；最终封装使用官方 `--strip`。
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

## 管理器自身更新源

Pro 的应用内更新只查询 `vring99/BakaSU`，不会回退到官方仓库：

- 稳定版查询本仓库的最新正式 Release，只识别 `BakaSU_Pro_...-release.apk`。
- 测试版查询 `codex/build-35233` 分支的 `build-private-manager.yml` 成功构建，包含手动触发的构建。
- 测试版下载最终重新打包、签名的 `BakaSU-Pro-release`，不是中间 Gradle 产物。
- APK 匹配支持 `arm64-v8a`、`armeabi-v7a`、`x86_64`、`riscv64` 和 `universal`。

未发布正式 Release 时，稳定版通道不会显示更新；Actions 产物过期后需重新构建。
覆盖安装仍要求相同包名、相同签名和更高版本号。要更新现有安装，请在构建的
`package_name` 输入原包名；留空仍按原规则生成随机包名，属于另一款应用，不能覆盖旧包。
这次修改只有在重新编译、安装新 APK 后才会生效，已安装的旧管理器不会被源码修改自动改变。

## 接入 GKI 内核编译

本仓库的 Actions 编译管理器和 LKM；GKI 的完整内核镜像继续由你的 GKI 内核仓库编译。
推荐直接使用本分支的 kernel 源码，签名及权限收紧已内置，不需要重复应用私有补丁。
外部构建使用官方 **d5e9e025b8b49155f8014684d64c91742b465f65** 为基线时，Actions 导出
`gki-manager-signature.patch`，仅包含 Pro 签名、渠道署名和信息查询权限所需文件。
同步上游后，补丁基线也已更新；新补丁不再面向官方 35229，避免遗漏新代码生成器和内核功能依赖。
仓库内的旧副本 `docs/patches/gki-manager-signature-35229.patch` 仅为历史记录，
不代表当前原生 SUSFS 接入代码；两者不能混用。
应在 BakaSU 源码拉取后、真正编译前应用（命令在 BakaSU 源码根目录运行）：

```bash
git apply --check /path/to/gki-manager-signature.patch
git apply /path/to/gki-manager-signature.patch
```

如果使用本分支源码，直接使用已有的私有认证代码，不要重复应用补丁。
`kernel/setup.sh` 已恢复官方版本，不能用它的默认远程地址安装 Pro。
需要私有身份时显式克隆 `vring99/BakaSU` 的 `codex/build-35233` 分支，
或向上述固定官方基线应用本次导出的补丁。接入时必须确认实际源码提交。
编译配置保持：

```text
CONFIG_KSU=y
CONFIG_KSU_MULTI_MANAGER_SUPPORT=n
```

### GKI + SUSFS 接入边界

本次恢复了官方 35252 的 SELinux、preinit、SUSFS 接口检查和代码生成逻辑。
此前 Pro 针对新版 SUSFS 增加的适配文件、额外 nolibc 架构头和模块 preinit 状态 UI
已撤销，可从旧提交 `54983206` 恢复。`PREINIT.md` 仅保留为旧实现的历史说明。

这意味着先前依赖 Pro 扩展接口的外部 GKI/SUSFS 构建不能直接假定仍兼容。
完整 GKI 构建和刷机不在本次范围；需要以实际内核源码及 SUSFS 补丁重新验证。
不要删除官方兼容性检查来强行编译。本仓库 Release 工作流验证管理器和 LKM，
不代表任意外部 GKI/SUSFS 组合已经通过编译或开机测试。

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
python scripts/private_manager.py gki-patch --output dist/gki-manager-signature.patch
```
