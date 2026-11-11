## 简体中文

下载 **BunnyInfo-v3-Windows-x64.zip**，完整解压后双击 **BunnyInfo.exe**，浏览器自动打开。关闭小启动窗口即可退出。无需安装 Python、依赖或使用命令行，请保留 `_internal` 文件夹。

v3 新增 ComfyUI 工作流模型盘点与 Civitai 哈希查询：

- 单项或批量查询，最多 3 路并行，匹配结果直接显示在应用内并链接到对应模型版本。
- 盘点工作流中可识别的 checkpoint、LoRA 和扩散模型，保留节点来源；模型列表不代表启用状态。
- 缺少哈希、未找到、网络失败、访问受限和限流分别提示，支持适当重试。

仅在点击查询时联网，不上传图片或提示词。只有文件名、没有哈希的模型可以列出，但无法按哈希查询。

升级前退出程序并备份 `data/`，把整个 `data/` 复制到新程序旁即可保留收藏。旧收藏首次升级写回前会生成数据库备份；解除收藏不影响旧备份。

程序未签名，Windows 可能提示未知发布者。支持 Windows 10/11 x64，附 SHA-256 校验。自动生成的 Source code 是源码，普通用户请选择 Windows ZIP。

## English

Download **BunnyInfo-v3-Windows-x64.zip**, extract the entire archive and open **BunnyInfo.exe**. Your browser opens automatically; close the launcher window to exit. No Python or dependency installation is needed. Keep `_internal` beside the executable.

v3 adds ComfyUI workflow model inventory and Civitai hash lookup:

- Query individual models or batches with up to three concurrent requests, inline results and exact-version links.
- Inventory recognized checkpoints, LoRAs and diffusion models with node origins. Listed references do not imply active models.
- Distinct missing-hash, not-found, network, access-restriction and rate-limit feedback with appropriate retry controls.

Only explicit lookups contact Civitai; images and prompts are not uploaded. Filename-only references are listed but cannot be looked up by hash.

Before upgrading, close the app, back up `data/`, and copy the entire folder beside the new executable. A database backup is made before old favorites are upgraded. Deleting a favorite does not change old backups.

Unsigned Windows 10/11 x64 build; SHA-256 checksums are provided. The automatic Source code downloads are developer archives; choose the Windows ZIP for the ready-to-run app.
