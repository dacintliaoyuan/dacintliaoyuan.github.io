# 原图处理流水线

此工具把来源调查、选图、去字结果、裁剪、High Fidelity 放大和验收串进一份可续跑队列。新队列位于本机 `.local/output/adashima-art/art-pipeline/pipeline.json`，不入 Git。旧日期批次作为档案保留，新流程不再改写它们。

用户负责选图与最终验收。程序提供提名、处理和证据，不替用户决定保留哪张，也不删除原图。`selected` 是进入处理的选择，`approved` 是针对具体处理稿的验收，两者分别保存。

## 已导入的内容

2026-10-16 导入既有批次的 45 项记录：38 张已选、已验收官方图，1 张暂停的 #87，6 张移除记录（#24～#28、被86A／86B替代的旧#86）。采用稿按实际文件、尺寸与 SHA-256 复用；不会重新运行 GPT 或 Upscayl。网站依然使用原先验收的背景池。

`seed-legacy-evidence` 只读取保存的研究 JSON，并记录证据文件哈希、历史日期和访问结果；不联网、不声称已经查完某个账号或平台。来源状态如下：

| 状态 | 含义 |
| --- | --- |
| `not_checked` | 尚未登记此页面或注明范围的检查 |
| `checked` | 已有具体观察，尚不能断言取得最佳原图 |
| `access_restricted` | 该次请求受限；不表示没有原图 |
| `only_preview` | 检查范围内只有封面、宣传或商品预览 |
| `original_found` | 人工核对后确认找到原稿 |
| `no_match_found` | 在记录的范围内暂未找到 |

自动下载只请求明确提供的图片 URL，不猜地址、不接管账号登录。失败状态会保存，HTTP错误页不会当成图片。成功下载先作为新候选；确认更好后用 `set-source` 登记，旧稿和旧配方保留，新稿需要重新验收。

## 使用入口

从仓库根目录运行下列命令。Python 等价入口是 `python tools/art_pipeline.py`。`--library`、`--work` 和 `--home` 是可选全局参数，放在子命令前；不传参数时使用本项目路径。

```powershell
tools/art_pipeline.bat status
tools/art_pipeline.bat analyze
tools/art_pipeline.bat report
```

只查看当前同人批次用 `report --kind fan`，只查看官方素材用 `report --kind official`。分类报告的导出只包含该类素材，导入不会改另一类的选择和验收记录；两类仍由同一份队列管理，后续采用时共同保留在背景池中。

双击 `.bat` 会显示当前状态和常用命令。首次创建空队列用 `init`；本机当前队列已初始化，不应重复初始化。新电脑保留原图库后可运行：

```powershell
tools/art_pipeline.bat init
tools/art_pipeline.bat import-restoration
tools/art_pipeline.bat seed-legacy-evidence
```

报告可直接打开生成的 `index.html`；通过本机图库服务查看时，地址为 `http://127.0.0.1:8765/art-pipeline/reports/<reportId>/index.html`。服务未运行时，在项目根运行 `python -m http.server 8765 --bind 127.0.0.1 --directory .local/output/adashima-art`；已有服务时复用，不重复启动。

## 一张新图的完整闭环

1. `add-image` 加入候选，默认待选择。`analyze` 提出同文件、同像素、近似重复、黑白和低清候选，保留所有选项。
2. `report` 生成并列浏览页、来源表与原尺寸详情页。可以切换原图和处理版本、适应窗口／100%／200%放大及拖动。网页只保存本轮草稿；导出 JSON 后用 `apply-decisions` 写入队列。
3. 确认去字范围、白边和是否放大后，使用 `plan` 登记明确配方；不会自动猜测文字或裁掉内容。
4. `run` 只处理已选择的图片。无字稿跳过去字；GPT任务停在 `waiting_gpt`，提示词和输入指纹输出到 `gpt-jobs/`。由当前执行者调用已授权的图片编辑工具，取得结果后用 `record-clean` 登记实际 PNG。
5. 如有灰度遮罩，只将遮罩区域的 GPT 结果合回原图；源图、编辑图、遮罩必须同尺寸，遮罩外保留原像素。没有遮罩则保留整张编辑结果，不自动对齐、缩放或声称遮罩外未改动。
6. 再次 `run`，执行明确裁剪和本机 Upscayl High Fidelity 2倍放大。默认已有长边达到3000像素时跳过放大；不强求每张输出3000像素。模型、命令、耗时、退出码和文件哈希保存到处理收据。
7. 重新 `report`，用户验收当前采用版本后导出并导入。改变输入或配方会使旧验收失效。`publish` 只消费当前已选且验收有效的集合，更新本机主页背景；不上传网站。

示例命令（示例路径需替换为真实文件）：

```powershell
tools/art_pipeline.bat add-image --id "new:example" --file "D:/pictures/example.jpg" --title "新候选" --artist "画师" --link "https://example.org/art" --official
tools/art_pipeline.bat analyze
tools/art_pipeline.bat report
# 在网页选择并导出，然后导入选择：
tools/art_pipeline.bat apply-decisions --file "D:/download/art-pipeline-decisions.json"
tools/art_pipeline.bat plan --id "new:example" --text gpt --prompt-file "D:/pictures/remove-text.txt" --mask "D:/pictures/text-mask.png" --crop 10 20 990 1400 --note "只去书名，裁掉外侧白边，保留画内签名"
tools/art_pipeline.bat run --id "new:example"
# 查看 gpt-jobs 中该任务的 key，取得对应 PNG 后登记：
tools/art_pipeline.bat record-clean --id "new:example" --file "D:/pictures/clean.png" --job-key "任务JSON中的key"
tools/art_pipeline.bat run --id "new:example"
tools/art_pipeline.bat report
# 用户逐图验收并再次导出后：
tools/art_pipeline.bat apply-decisions --file "D:/download/art-pipeline-decisions.json"
tools/art_pipeline.bat publish
```

无需去字使用 `--text none`；无需放大加 `--no-upscale`。裁剪矩形采用左闭右开像素坐标 `[left, top, right, bottom]`，相对于去字后的图片。配方登记先按源图检查范围；如果 GPT 整图结果改变尺寸，后续裁剪仍会再次校验，越界会停止，需核对后重设配方。放大只使用本机已有的 High Fidelity 文件，不下载安装，不使用 anime-seg，也不调用文生图重新构图。

## 来源与续跑

```powershell
tools/art_pipeline.bat source-add --url "https://example.org/artist" --title "作者主页，检查指定作品范围" --category author
tools/art_pipeline.bat source-note --id "source-add返回的id" --status only_preview --note "检查了活动页和对应商品页，目前只有带SAMPLE预览" --evidence "实际页面与检查范围"
tools/art_pipeline.bat download --id "new:example" --url "https://example.org/image.jpg"
tools/art_pipeline.bat set-source --id "new:example" --file "下载命令返回的图片路径" --note "核对同构图，采用分辨率更大的作者稿"
tools/art_pipeline.bat run --retry --id "new:example"
```

成功结果缓存绑定输入、配方、处理代码和模型文件；续跑核对哈希后复用。失败项默认保留失败，需要 `--retry`；暂停、移除和待选项不运行。重新下载同 URL 默认复用已经核验的下载文件；需要重新请求时显式加 `--refresh`。更换源图、裁剪或去字版本不会覆盖旧输出。

本机 Upscayl 原生程序在约300字符的输出路径下实测崩溃，同一输入和模型在短路径下正常。适配器因此将推理输入与输出放入图库根部的私有短目录，核验后再归档到深层缓存，并清理本次临时目录；不依赖 Windows 长路径支持。若图库根路径本身过长，会在启动模型前明确报错。

队列独占锁避免两个执行者同时处理同一队列。普通异常和 Ctrl+C 会释放锁；进程被强制结束留下锁时，先 `status` 看 PID/token，确认现场后用 `recover --token "..."`。工具仅在确认该 PID 已结束且 token 未变时释放本队列锁，不删除图片缓存或网站锁。

`publish` 在私有目录生成候选背景池、采用清单和网站素材，复核正式目标未变后切换，保存前一份对象和事务日志。失败尝试回滚；未知外部改动拒绝覆盖。切换要给 `site/assets` 改名，Windows 上只要有进程正用着它（例如终端的当前目录停在里面），就会报 WinError 32 并回滚；换个目录后重新 `publish` 即可（2026-10-21 遇到过一次）。中断的发布按日志用 `recover-publication --journal ".../journal.json"` 恢复。队列写盘失败不抹去已经成功的网站事务，可以再次发布同一集合核验并同步状态。已经一致的背景池只核验并返回 `unchanged`，保留原文件字节。采用主稿保持原尺寸；网站派生图遵守现有 `build_assets.py` 的压缩与显示契约。清晰层的编码契约改过一次（2026-10-21：由最高 2160 像素、q90 改为 q95，比 2160 像素高的图另出一份原尺寸的）：按旧契约生成的现有清晰层会被认出并重建，对不上任何契约的清晰层仍按外来改动拒绝覆盖。

2026-10-22 仓库移出 personal_files：此前三次发布的 journal 和队列里的 `integrated.journal` 记的是旧位置的绝对路径，只作历史；三次都已完成，`recover-publication` 因工作目录不同会拒绝它们，属预期。

`clean-report --id "report命令返回的reportId"` 只处理本队列登记的生成报告：先压缩并校验，再清理报告页面和缩略图；有用户新增文件、哈希改变或路径不符时拒绝清理。原图、处理稿、提示词、队列、模型与正式网站资产都不在此清理范围。

## 验证与限制

验证入口：`python -m unittest discover -s tests -q`，覆盖队列续跑、来源失败、图片处理、网页导出以及发布回滚；真实 GPU 和浏览器交互需分别验证，模拟进程成功不能代替真实 Upscayl 运行。

当前版本自动化本机整理与处理调度。全网检索、账号登录、作品同构图判断、去字范围判断和最终视觉验收仍由人或当前执行者完成。GPT没有配置无人值守API；程序生成任务、登记编辑结果、继续后续处理。相似度与色度指标只能提名，不能判断某张更值得保留。
