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
GKI 构建必须使用本分支的 kernel 源码，或在拉取官方 **35229** 后，应用
`gki-manager-signature.patch`。仓库内预备副本为
`docs/patches/gki-manager-signature-35229.patch`，也会随构建产物导出。
补丁包含签名白名单、公开证书、多管理器默认值和对应构建日志。
应在 BakaSU 源码拉取后、真正编译前应用（命令在 BakaSU 源码根目录运行）：

```bash
git apply --check /path/to/gki-manager-signature.patch
git apply /path/to/gki-manager-signature.patch
```

如果使用本分支源码，直接使用已有的私有认证代码，不要重复应用补丁。
上游 `kernel/setup.sh` 会拉取官方仓库；仅将脚本下载地址换为你的仓库并不会切换内核源码来源。
应明确替换 GKI 工作流中的源码 clone / checkout 步骤，或在上游 setup 完成后应用本补丁。
编译配置保持：

```text
CONFIG_KSU=y
CONFIG_KSU_MULTI_MANAGER_SUPPORT=n
```

LKM 流程对应 `CONFIG_KSU=m`，证书校验代码相同。不设置固定 `KSU_MANAGER_PACKAGE`，
否则新随机包名可能被包名过滤提前拒绝。

只安装本管理器而未重编 GKI/LKM，不会改变设备上旧内核接受的管理器签名。
源码检查、管理器构建均不代替真实 GKI/LKM 编译、刷入和设备验证。

修改上述内核认证文件后，在本仓库重新生成补丁：

```powershell
python scripts/private_manager.py gki-patch --output docs/patches/gki-manager-signature-35229.patch
```
