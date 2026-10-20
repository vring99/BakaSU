# 模块 preinit

本实现移植自官方 KernelSU 提交
[`0faec0cc`](https://github.com/tiann/KernelSU/commit/0faec0cc7b5f655170d89bf9c4d28bb5ca271fa2)，
包含 [`e9ef3540`](https://github.com/tiann/KernelSU/commit/e9ef3540a0dc40db6743e9f619bf0066f78fad34)
的 Linux 6.19+ 兼容更新，并接入 SUSFS 官方的内联调用接口。

## 执行时机

首次启动阶段执行 `/system/bin/init selinux_setup` 时，内核临时交给内嵌 runner。
此时 `/metadata`、`/system`、`/vendor` 已挂载，`/proc`、`/sys`、`/dev` 可用，
SELinux 策略和 init.rc 尚未加载。runner 完成后继续执行正常的 Android init。

使用 SUSFS 或 Tracepoint Hook、正常启动的 GKI 和 LKM 可以接入。
手动 Hook 和系统启动后才加载的 late-load 不支持 preinit。
缺少目标内核 UAPI 头文件或设置 `preinit=0` 时也不启用。

## 模块格式

模块内创建 `preinit/`，其中必须包含 `preinit.conf`。ksud 将已启用模块的这个目录
同步到 `/metadata/vold/ksu/preinit/<模块 ID>/`，不可用时依次选择
`/metadata/watchdog/ksu/` 和 `/metadata/ksu/`。更改在下次启动时执行。

每行一个动作，模块按 ID 排序。支持以下动作：

| 动作 | 语法 | 用途 |
| --- | --- | --- |
| 加载内核模块 | `insmod <ko> [参数...]` | 提前加载模块；必要的内核符号查询仅允许 root 调用 |
| 执行程序 | `exec [-t <毫秒>] <程序> [参数...]` | 执行静态程序并等待退出，默认超时 5000 毫秒 |
| 写入文件 | `write <路径> <内容>` | 向已有文件写入内容，不自动添加换行 |

相对路径以模块的 preinit 目录为基准。支持双引号及引号、反斜杠转义，不进行变量展开。
空行和以 `#` 开头的行被忽略。动作名后加 `?` 表示允许失败；其他动作失败时中止
当前模块的剩余动作。单行上限 4 KB，配置文件上限 64 KB。

这一阶段不能依赖 `/data`、Android property service 或普通 Android shell 环境。
安装、禁用、删除、更新模块和执行 `ksud initrc refresh` 时会重新同步内容。

## 失败恢复

runner 保留官方的空间限制、root 文件所有权检查、执行超时和失败启动计数。
连续三次启动未完成后跳过 preinit；充电模式跳过执行且不增加计数。
成功完成启动后清除正常计数，已因启动失败停用的状态保留，直到内容变化或手动恢复。

```sh
ksud module preinit status
ksud module preinit reset
```

管理器显示空间不足、同步错误、启动失败后停用或内核不支持的状态。
修补 boot 时可用 `--no-preinit` 关闭；GKI 内置模式使用内核参数 `kernelsu.preinit=0`。

主机源码、接口和链接测试不能代替全量内核编译与真机开机验证。
