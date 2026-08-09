# CLAUDE.md

给下次会话接手用的状态记录。项目整体背景见 [README.md](README.md)。

## 现在在干什么

给"俯视栅格"离线验证管线（`topdown_pipeline.py`：metric深度→点云→地面拟合→10×9俯视栅格）做**相机标定 + 测试集精度验证**。详细协议、算法改动、完整数据表都在 **[TOPDOWN_VALIDATION.md](TOPDOWN_VALIDATION.md)**——这是主记录，下次先看那个。这份文件只写"现在卡在哪、下一步干什么"。

## 当前状态（2026-08-09 会话结束时——对照实验已跑完，假设基本坐实）

- fx=3260px 已标定确认，不用重拍。
- 地面拟合算法已收紧（候选带45%→25%，非对称容差[-15,+5]cm，2轮→3轮迭代）+ 尺度锚定（`CAM_H_TRUE=1.40m`）+ 健康指标（`scale` 离散度CV，<10%才算干净）。
- **补拍的3张对照照片（`empty3`/`chair_3m_plain`/`balloon_1m_plain`，地面是浅蓝环氧地坪+近处一块深色胶垫的混合场地）跑完，结论：黑色/深色地面材质假设成立**：
  - 椅子3m 落在浅蓝地坪范围内 → 估距误差从黑布组的 -14.0% 降到 **-2.1%**。
  - 气球（标称1m，压在浅蓝地坪上）→ 测得深度 **1.63m**，和"相机高度1.4m+水平1m"的纯几何直线距离预测值 1.72m 几乎精确对上（黑布组同类气球测出3.1-3.6m，差2-3倍）。
  - `scale`/`cam_h_raw` 这两张依然没回到 ~1.0（还是 0.66-0.69，CV=14.0%），但逐行查过：RANSAC地面候选带（画面底部25%）在这两张新照片里material分界线正好卡在候选带起点，候选带几乎整个落在近处那块深色胶垫上，**不是假设被推翻，是候选带这次恰好又踩进了另一块深色材质**——和黑布组是同一类问题，只是范围缩小到了画面最下方一条，没盖住椅子/气球所在的浅蓝区域。这正好解释了"物体测距准了、但scale没变"这个看似矛盾的结果。
  - 完整数据表和材质分界线的逐行验证过程见 [TOPDOWN_VALIDATION.md](TOPDOWN_VALIDATION.md) "决定性对照实验结果" 一节。
- **结论：俯视管线算法本身没问题，是黑色/深色反光地面材质让 Depth Anything V2 近距离绝对尺度失准。以后测试集/实际部署选浅色、非反光地面拍摄，且要确保画面最下方（相机脚下那一截，RANSAC候选带覆盖的范围）也不能是深色材质。**

## 下一步（可选，非阻塞）

对"地面拟合算法本身scale能否回到~1.0"这一点，三次尝试（黑布组×2 + 新拍组）候选带都不巧踩在深色材质上，还没有一张"从画面最下方到远处全程浅色地面"的干净样本。不是必须——现有证据已经足够支撑"换浅色地面部署"这个操作结论。如果 Hsinlung 想彻底闭环，可以再补拍一张连脚下都是浅色地面的照片；否则可以直接往下走（比如把俯视栅格接入实际胸挂设备）。

## 环境注意事项（踩过的坑，别重踩）

1. **这台机器 `D:\anaconda\envs\lingtouch` 的 numpy LAPACK 库整体是坏的**：`np.linalg.{svd,eigh,inv,det}` 或大数组 `@`/`np.dot`（N≳1000）会**静默崩溃**（退出码127，无 traceback）。matplotlib 的 `savefig` 也会中招（内部要求逆变换矩阵）。已在 `topdown_pipeline.py` 里手写绕开（`matvec`/`smallest_eigvec_3x3`/`_det3`），但**新加代码如果用到矩阵运算要小心**；`topdown_pipeline.py --outdir` 那段可视化目前跑不通。建议找时间重装这个环境的 numpy/BLAS 彻底解决。
2. **中文文件名 + Git Bash + Windows Python = 乱码**：`cv2.imread` 等直接拿命令行参数传中文路径的场景会失败且报错信息本身也是乱码，容易误判。测试图片一律先在 Python 内部（`shutil.copy2`，不经过命令行参数）复制成 ASCII 文件名再处理，见 `pics/ascii/`。
3. 跑深度推理/矩阵运算用 `D:\anaconda\envs\lingtouch\python.exe`（不是 `where python` 默认给的那个，那个是 anaconda base，没装 torch/cv2）。
4. `Depth-Anything-V2/`（官方仓库clone + `metric_depth/checkpoints/depth_anything_v2_metric_hypersim_vitl.pth` 1.3GB权重）、`pics/`（标定+测试集照片，484M）都在 `.gitignore` 里，本地存在但不进 git，是正常状态，不是遗留垃圾。

## 坑：`git clone` 出来的 `Depth-Anything-V2/` 自带独立 `.git`

`git clone` 官方仓库时会带着它自己的 `.git`，等于在项目文件夹里嵌了个**独立的第二仓库**（指向
`github.com/DepthAnything/Depth-Anything-V2`，跟我们项目无关）。它自己没有 `.gitignore`，所以从
它自己的视角看，`metric_depth/checkpoints/*.pth`（1.3GB权重）永远是"未跟踪"状态——VSCode
Source Control 面板会把这个嵌套仓库当成额外的仓库单独显示出来，看着像"权重文件要被提交了"，
其实跟主仓库完全无关（主仓库的 `.gitignore` 里 `Depth-Anything-V2/` 整体忽略，包括它的 `.git`
本身，不可能泄漏进主仓库历史）。2026-08-09 已经把这个嵌套 `.git` 删掉（`rm -rf
Depth-Anything-V2/.git`），消除这个视觉困惑；如果以后重新 `git clone` 覆盖了这个目录，这个坑会
再出现一次，记得再删一次，或者当时就用 `git clone --depth 1 <url> tmp && cp -r tmp/* dest && rm -rf tmp`
这种方式避免带 `.git`。

## Git 状态（2026-08-08 审计过，干净）

检查过 `git ls-files`，62个跟踪文件全是合法源码/文档/两张小参考图（`vision/1.jpg`/`2.jpg`），没有 `pics/`、`Depth-Anything-V2/`、`.npy`、`.pth`、`node_modules`、`__pycache__` 等被误提交。当时看到"很多东西"大概率是编辑器 Source Control 面板把**未提交的修改/新文件**（`.gitignore`、`README.md` 的改动 + 这次新加的 `TOPDOWN_VALIDATION.md`/`topdown_pipeline.py`/`validate_distance.py`/`check_balloon_depth.py`）显示成一大坨，不是已提交的垃圾——这些新文件本身就是这次会话的产出，还没 commit，不要删。
