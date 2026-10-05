# 国赛眼镜硬件方案 v10（2026-10-02）

本文件记录当前硬件组成、用途和连接依据。部件类别与功能分工已基本明确；没有查到必须推翻整体架构的硬件冲突，但尚未完成整机验证。当前不继续搜索具体商品型号，也不展开固件、采集参数或算法实现。

## 已定方向

- 继续采用 **CS30＋Radxa ZERO 3W**，相机、主板、电池等都放在眼镜上。
- **预警和障碍分析都用这副眼镜的数据。计算位置仍在权衡：** 眼镜采集后经 Wi-Fi 发手机计算，或眼镜本地计算、只把结果发手机。两种做法眼镜上的器件相同；外壳散热按眼镜本地计算的满负荷预留，计算位置最后怎么定都不用改壳。
- **全机免焊：** 优先购买成品模块、成品电源及预制线束，需要焊接或装配的部分尽可能由卖家或代工完成；不自行制作电池组，不另做自研主控 PCB。
- **电池尚未定型，已查资料保留在第四节。** 整机以单个Type-C接口输入稳定5V供电为目标，优先5V/3A成品电源；内部向主板及相机分电的成品连接方案尚未定完整。成品候选、代工入口和续航估算用于后续比较，不代表已经选定或完成装机验证。
- **整机约300g可接受；电池位置不受限，必要时做成头环、电池放后脑。**
- 学生项目，支持一定的室外使用，不要求覆盖强烈日光下的所有场景。
- **声音和麦克风改用单独的蓝牙耳机，直接连手机；头戴件上不放麦克风、功放、喇叭。**

## 硬件分工与 WOAD 参考边界

| 部件 | 用途 | 是否另需驱动板 |
|---|---|---|
| CS30成品相机 | 获取深度、红外和彩色数据 | 已包含相机内部电路，不另加相机或红外发射驱动板 |
| ZERO 3W | 读取传感器、处理数据、通过Wi-Fi与手机通信 | 本身就是主控板；本地全部算法的性能尚未验证 |
| IMU模块 | 测量头部转动与倾斜，为姿态补偿提供数据 | 3.3V接口匹配的成品模块可直接接I²C，不另加电平转换板 |
| USB连接与供电分配件 | 连接相机和主板，并向各部分分电 | 需要匹配的成品连接方案；单个Type-C入口不等于内部无需分电 |
| 散热件、外壳、支架、线束 | 散热、固定器件、保持安装关系、保护连接 | 按实际器件和佩戴条件落实 |

[WOAD论文](https://www.nature.com/articles/s41467-025-58085-x)采用CS30、ARM板、用于压缩策略加速的FPGA，以及耳机和三颗贴肤振动马达。我们保留CS30＋ARM主板的基本分工；基础采集与传输不以增加FPGA为前提，但不能据此继承WOAD的整机功耗、延迟和续航结果。触觉输出沿用本项目已有的独立触觉装置，当前清单不新增额头/太阳穴振动马达。外接Wi-Fi天线暂为可选件。

## 一、眼镜上必须有的东西

| 器件 | 当前选型 / 数量 | 用途与安装要点 |
|---|---|---|
| 深度＋彩色相机 | **Synexens CS30 ×1** | 提供深度、红外和彩色数据。带壳约 **89.94×30×25mm、74g**；已有官方 STP。前部安装，**镜头整体下倾约20°**：按镜头离地约1.6m计算，深度视场（上下75°）下沿可见脚前约1m的地面，上沿高出水平线约17°；彩色视场（上下59.5°）上沿高出水平线约10°。这是几何覆盖估算，不是障碍检测保证；IMU能提供姿态补偿依据，但不能补回视野外的图像。**镜头正前方直接开孔，不加普通透明罩**，避免ToF内部反射干扰。平均约3W。 |
| 采集与无线主板 | **Radxa ZERO 3W ×1，2GB＋16GB eMMC、已焊排针；原候选SKU RS107-D2E16H1W15** | USB读取相机、读取IMU、Wi-Fi通信。采购时另核实双频无线硬件版本：官方说明早期AP6212仅2.4GHz，V1.12I为双频Wi-Fi 6，不能仅凭内存/SKU认定无线版本。板面 **65×30mm**。USB2.0 OTG口作供电口，USB3.0主机口接相机。主机口标称500mA不足以覆盖CS30平均约0.6A需求，相机需另安排供电路径。排针与杜邦头高度按实物留位，原估算含线弯约20mm。 |
| IMU | **ICM-42688-P成品模块 ×1；具体商品暂不定** | 保留已核对接口的 [LogicalEdges Qwiic板](https://www.elecrow.com/icm-42688-p-ultra-low-power-imu-breakout.html) 作为参考，不视为必购商品。若采用该接口，可用Adafruit 4397（Qwiic转杜邦母头，150mm）：红3.3V、黑GND、蓝SDA、黄SCL。拟接 **I2C4-M0：物理27脚SDA、28脚SCL**。IMU与相机固定在同一刚性支架上；不能靠IMU单独长期准确估计位移。 |
| 相机数据与独立供电 | **需要此功能；8086 Consultancy USB-C/PWR Splitter作为已研究候选** | [厂商接线表](https://lectronz.com/products/usb-c_pwr-splitter)：DATA口只通D+/D−与GND，CC为5.1k下拉，5V不与主机相通；DATA/POWER口带5V，CC为10k上拉，接CS30；POWER口进5V。仅用于5V设备，厂商明确其不属于标准USB方案，与本机组合尚未验证。它负责相机的数据/电源合路，不能单独解决整机一个入口向多路分电。 |
| USB线 | **支持USB2.0数据的成品线；数量、接头及长度随分电方案确定** | 相机数据链路不能使用仅充电线。主板与相机附近优先短线，弯头方向及插头占用空间按实际安装确认。 |

## 二、外壳先预留，具体安装待验证

| 器件 | 候选 | 当前状态 |
|---|---|---|
| 散热件 | **Radxa Heatsink 5519A ×1** | [官方适配ZERO 3W/3E的散热件](https://radxa.com/products/accessories/heatsink-5519a/)。完整尺寸以实物为准。有用户反映装了它仍明显发热；外壳散热按眼镜本地计算的满负荷预留，CS30 与 Radxa 都不整体封死。 |
| 外接 Wi-Fi 天线 | **Taoglas FXP830.07.0100C ×1，可选** | [官方产品](https://www.taoglas.com/product/freedom-fxp830-2-44-9-6-0ghz-flex-pcb-antenna-ipex-mhfi-2/)。FPC约42×7mm、100mm馈线、U.FL/IPEX MHF1，覆盖2.4/5GHz。是否装用由佩戴传输测试决定；使用时按[Radxa外置天线说明](https://docs.radxa.com/en/zero/zero3/accessories/zero3w-antenna)切换配置。避开电池及散热金属遮挡。 |

## 三、接线（全部插接，不焊）

### 电源与 USB

| 从 | 线 | 到 |
|---|---|---|
| 整机Type-C 5V入口 | 成品分电件，待定 | 主板与相机供电分支 |
| 主板5V分支 | 接头/线束待定 | Radxa USB2.0 OTG口（供电） |
| 相机5V分支 | 接头/线束待定 | 候选Splitter POWER口 |
| Radxa USB3.0 主机口 | C对C短线 | Splitter DATA 口 |
| Splitter DATA/POWER 口 | C对C短线 | CS30 |

此表是目标连接关系，不是已落实的完整单口供电装配方案。原PB2S两口分别给主板和相机供电的接法不再作为当前默认方案。外部电源、内部电流余量、充电与开关机方式留待供能讨论恢复后确定。

### Radxa 40针排针（物理脚号）

| Radxa 脚 | 接到 |
|---|---|
| 1（3.3V） | IMU（Qwiic 红） |
| 6（GND） | IMU（Qwiic 黑） |
| 27 | IMU SDA（Qwiic 蓝） |
| 28 | IMU SCL（Qwiic 黄） |

## 四、电池与供电选型资料（已研究，尚未定型）

以下保留本轮查到的可用资料及链接，核对日期为2026-10-01。研究比较以轻量成品电源和厂家整包代工为主；没有选定电池、下单或联系厂家。已有候选不因“暂不定型”而删除，也不把尚待核实的商品当成直接可用的最终方案。

### 4.1 对成品电源的要求

| 项目 | 本项目要求或比较方法 |
|---|---|
| 交付范围 | 厂家完成电芯组装、充电、保护、5V稳压输出、封装及测试，我们只插线和安装。单卖裸电芯、保护板或升压板不算完整交付。优先国内成品或接受少量打样的OEM。 |
| 输出电压 | 稳定5V；主板和当前相机供电链路不使用9V/12V。电源可以具备快充功能，但本机连接只用5V，不增加高压诱骗模块。 |
| 输出能力 | **优先5V/3A连续输出**，为启动、无线发射峰值留余量。这是电源能力筛选值，不是整机平均功耗15W。只有5V/2A的轻量款保留为条件候选，须确认实际峰值和低电量下仍有余量。 |
| Type-C行为 | 必须支持对外供电而非仅输入充电，能通过C对C线正常启动、持续运行；明确低负载自动关断、唤醒及低电量关机行为。无需电池数据通信或专有系统绑定。 |
| 内部分电 | 目标为一个整机Type-C入口，内部再分给主板及相机。现有8086 Splitter是相机数据/电源合路件，不是完整多路分电器；分电件需适配Type-C识别、线缆载流与电压降，并避免向主机USB电源回灌。 |
| 能量口径 | 同时记录电芯标称Wh和**5V端额定/实测输出Wh**；不能把3.6V或3.7V标称mAh直接按5V计算。比较实际输出时注明测试电流、模式和地区版本。 |
| 重量与形状 | 统计完整电源的电芯、保护、充电/稳压电路和外壳重量；线材与固定件另计后纳入整机。可用扁平或圆柱形、后脑头带安装；约300g是整机接受方向，电池暂无硬性80g指标。 |
| 保护与机械 | 成品应有过充、过放、过流、短路及温度保护说明，接口和封装适合随身固定。OEM提供完整尺寸、重量、接口位置、持续/峰值输出和测试报告。不能用裸电芯指标代替电源包指标。 |
| 暂非必需 | 不要求边充边用、UPS不断电、无线充电、9V/12V输出；未确认充电时输出连续性的产品按停机充电考虑。 |

要求依据：[Radxa 5V供电及接口说明](https://docs.radxa.com/en/zero/zero3/hardware-design/hardware-interface)、[CS30厂家对ARM主板外接供电的建议](https://tofsensors.com/products/rgbd-3d-camera)、[8086 Splitter连接表](https://lectronz.com/products/usb-c_pwr-splitter)。相机平均约0.6A；主板的实际瞬态负载仍需整机测量，不以旧的平均电流相加代替峰值检查。

### 4.2 已查成品候选

| 候选与来源 | 完整电源重量 / 外形 | 能量与5V输出 | 对本项目的价值与限制 |
|---|---|---|---|
| **[NITECORE NB10000 Gen4 国内版](https://www.nitecore.cn/product/nb10000gen4)** | **143±5g**，117×47×15mm，不含配件 | 电芯39Wh（等效10000mAh）；额定输出6800mAh@5V/3A，即**34Wh**；节能模式7200mAh@5V/1A，即36Wh。双USB-C，单口列有5V/3A，双口总输出5V/3A。 | 当前研究的轻量成品比较基准，未定为最终采购。扁平、比原PB2S组合轻；不能把22.5W快充功率当成5V档功率，也不能把36Wh节能模式数据套到任意负载。 |
| **[ISDT 艾斯特 PB40 mini / PB40C2M](https://www.isdt.co/pb4020mini.html?lang=hk)** | **165±10g**，64×47.5×28mm | 等效10000mAh，标称38.7Wh；额定6240mAh@5V/2A，即**31.2Wh**。双USB-C，输出规格含5V/3A。 | 较短、较厚，可比较后脑安装空间；双口同时输出上限、启停行为需按实际版本确认。不要与同页5000mAh的PB20 mini混淆。 |
| **[NITECORE Carbon Battery 6K 国内版](https://www.nitecore.cn/product/carbon_battery_6k)** | **88g**，直径22.8×90mm | 6000mAh/3.6V，即21.6Wh；国内页额定3500mAh@5V、典型1A，即**17.5Wh**。单USB-C充放电，最高**5V/2A**。 | 重量接近WOAD所称80g，圆柱适合头带侧后方；能量更少，且不满足优先3A的筛选值，只有负载验证有余量后才适合使用。海外资料曾列18.5Wh，本表统一采用国内17.5Wh口径。 |
| **XTAR PB2S＋两颗Vapcell N40，原方案比较基准**：[PB2S原始实测](https://lygte-info.dk/review/Review%20Charger%20Xtar%20PB2S%20UK.html)、[N40厂家规格](https://www.vapcelltech.com/h-pd-193.html) | 盒体原记录约85g，测试样品86g；N40约48g/颗，合计约**181–182g**。测试盒体125×58×27.7mm。 | 两颗N40典型合计8000mAh/3.6V，即28.8Wh电芯能量，**没有这套组合已确认的5V输出Wh**。被测PB2S在5V可带额定2A，过载约2.7A；这不等于额定3A。 | 可更换电芯、免焊，但盒体重，不再作为默认方案。实测USB-C输出仅5V，使用C口时高压档关闭；双口合计额定能力未核实。测试还显示充电时输出不能保持正常5V，因此不作为UPS。PB2S/PB2SL及批次参数不能混用。 |
| **[微雪 Solar Power Manager (B)](https://www.waveshare.com/product/modules/solar-power-manager-b.htm)** | 先前查到108×71×25.2mm、金属外壳；完整重量待确认 | 内置10000mAh电池、充电管理和5V/3A输出；可用输出Wh未确认。 | 属于开发商城的完整供电产品例子，体积没有比上述轻量成品更适合头戴；保留作备选，不因带太阳能输入而增加太阳能板。 |

国内渠道：[奈特科尔天猫旗舰店](https://nitecore.tmall.com/)、[京东旗舰店](https://nitecore.jd.com/)来自国内官网入口；ISDT保留上述官网及[PB40C2M国内评测/购买跳转](https://chargedb.cn/PB40C2M)作为购买线索，成交价与库存未核实。XTAR、Vapcell和微雪可按品牌型号在国内官方渠道核对。此前淘宝搜索页被浏览工具的站点安全规则拦截，**没有核验具体淘宝店铺、销量或在售价格**。

### 4.3 续航与重量比较

计算式：**续航小时≈5V输出可用Wh÷整机在5V入口的平均W**。以下4/5/6W只是比较情景，不是我们已经测得的整机功耗；手机自行供电，其耗电不包含在眼镜电源预算中。既然使用5V输出能量，就不再重复乘一次电池升压效率；实际线损、截止条件、模式及负载变化仍影响结果。

| 候选 / 计算所用能量 | 平均4W | 平均5W | 平均6W |
|---|---:|---:|---:|
| NB10000 Gen4，常规模式额定34Wh | 约8.5h | 约6.8h | 约5.7h |
| PB40 mini，额定31.2Wh | 约7.8h | 约6.2h | 约5.2h |
| Carbon Battery 6K，额定17.5Wh | 约4.4h | 约3.5h | 约2.9h |
| PB2S＋两颗N40，**假设**28.8Wh×90%=25.9Wh | 约6.5h | 约5.2h | 约4.3h |

各厂家额定能量的测试电流不同，上表用于初筛，不是统一条件实测排名。PB2S行的90%仅是假设；原7000mAh容量预算同样按3.6V与90%计算时是22.7Wh，不应误写为N40组合实测容量。NB10000的36Wh节能档只在相应输出模式和负载允许时另行考虑。

若争取10h，4W平均负载需要至少40Wh的实际输出能量，5W需要50Wh，另外还要留实际损耗余量。34Wh电源要达到10h，平均入口功耗需约不高于3.4W；所以换轻量成品可以改善重量和容量，但不能单凭10000mAh标签承诺10h。

原PB2S＋N40约181–182g，对比NB10000 Gen4约143g，可减约38–39g，标称电芯能量由28.8Wh增至39Wh。与74g相机合计后，原组合约255–256g，新候选约217g；距离300g分别剩约44–45g与83g供其他器件、线束和外壳使用，**均不是整机最终重量**。后脑安装借鉴WOAD的前后配重思路，改善重心而非减少总重。

### 4.4 整包代工入口及交付要求

| 厂家 / 原始链接 | 已查到的能力 | 尚未确认的条件 |
|---|---|---|
| **[深圳沃尔德新能源](https://www.wpbattery.com/dianchipackdingzhi/)** | 官网给出电芯与BMS选型、结构/外壳/接口设计、打样、送样测试及批量交付流程，并说明随样提供规格书与测试报告。 | 是否接本项目一两套完整5V电源、输出升压/充电集成范围、成品重量、开发费、起订量与交期。仅有“支持定制”不能算已答应小单。 |
| **[援通电子](https://www.batteryodm.com/ldc/57.html)** | 页面列出带保护、5V输出、Type-C充放电的电池包定制。 | 写有100组起订，其他位置又列不同数量；小样条件不清。不是当前少量样机的优先入口，不能将宣传报价直接用于预算。 |
| **[PAC Battery 9000mAh / 5V USB电池包](https://www.pacbattery.com/rechargeable-lithium-polymer-battery-pack-9000mah-5v-with-usb-port-for-power-bank.html)** | 提供USB 5V输出电池包例子，尺寸和容量可定制；表中电芯为3.7V、9000mAh。 | 完整重量、USB端额定电流/输出Wh、Type-C接口、起订量和完整充电交付条件未确认。表中电芯侧18A参数不能当成USB输出能力。 |
| **[CM Batteries定制服务](https://cmbatteries.com/custom-battery-packs/)** | 提供电池包设计、组装、保护和测试；部分[产品页](https://cmbatteries.com/project/high-temperature-3-7v-4000mah-21700-battery-pack/)有样品/小批量线索。 | 是否愿接本项目、完整5V稳压及Type-C充电输出、最低数量、费用和交付重量仍需询价，不等于已验证供应商。 |

后续给厂家询价时，交付对象应明确为**可直接插接的完整5V电源包**。询价内容包括：5V/3A连续输出及启动峰值能力、所需5V输出Wh、头带允许尺寸与接口方向、全包重量、保护项目、C对C启动/自动关断行为、充电方式、样品数量、开发费、单价、交期、配套线束和测试报告。电芯内部串并联由厂家按目标设计；我们不限定必须两颗18650，也不接受让我们自行焊接集成的“半成品”。目前没有联系或下单。

### 4.5 WOAD电池证据与其他方向

- **WOAD可借鉴的是安装方式，电池型号仍未知。** [图2a](https://www.nature.com/articles/s41467-025-58085-x/figures/2)展示后脑位置的长条包膜电池并标注12000mAh，正文称电池约80g、眼镜约400g、续航约11h。本轮已查正文、补充材料、审稿回复和仓库，未找到电芯型号、完整电源电路及重量口径。若假设按3.7V计算，12Ah为44.4Wh，除以80g得到555Wh/kg；这是对标注的条件核算，不是已确认电池参数。因此不把“80g、10h+”写成现成采购指标。[论文](https://www.nature.com/articles/s41467-025-58085-x)、[公开仓库](https://github.com/MMCNJUPT/WOAD)
- **[Vapcell P2160B](https://www.vapcelltech.com/h-pd-256.html)**：此前找到的带USB充放电圆柱电源方向，保留厂家入口。使用者约79g、约15.4Wh的[原始测量记录](https://www.reddit.com/r/Ultralight/comments/1huwxgz)仅作线索，不作为额定保证；完整输出能力未补齐，不列为首选。两颗分别供电也不能不考虑负载分配就相加承诺续航。
- **[DFRobot DFR0446 / MP2636](https://www.dfrobot.com/product-1613.html)**：此前研究过的小型充电升压模块。它本身不是完整电源，不能恢复为让用户自行集成的方案；只可供代工方评估内部实现，最终仍须交付完整包。
- **[Amprius SiMaxx SA80初步规格](https://amprius.com/documents/Amprius_Product_Portfolio_0824_website.pdf)**：此前查到高能量密度硅负极电芯方向，但裸电芯之外还需夹持、保护、充电、稳压与封装，小批量成品渠道未确认。保留[可穿戴电池项目实例](https://amprius.com/amprius-to-integrate-safe-cells-into-next-generation-u-s-army-wearable-battery-pack/)作技术线索，不列入本项目直接采购清单，也不能据此推定WOAD使用这种电芯。

当前比较方向仍是：以NB10000 Gen4作为轻量成品基准，PB40 mini比较短厚外形，Carbon Battery 6K比较更轻但能量较少的取舍；若成品形状不合适，再按同一完整电源要求比较OEM。最终选择待整机负载与安装安排确定。

## 五、硬件检查结果与边界

| 检查项 | 本轮结论 |
|---|---|
| 相机与主板 | USB数据接口匹配、ARM64 SDK有支持路径；不另加相机驱动板。候选Splitter和整机连续出帧尚未实测。 |
| IMU | 电平和拟用引脚能对应，不需要通用电平转换板；联合运行未验证。 |
| 无线版本 | 需核实ZERO 3W实物为支持5GHz的版本，不能只凭板名、内存容量或外接双频天线推定。 |
| 供电连接 | 单个Type-C入口的内部成品分电方案尚未闭合；第四节已保留供电要求、成品/OEM候选和估算，电池仍未定型，整机供电余量未实测。 |
| 重量与体积 | 约300g是可接受方向，不是当前实测总重；电源未定，不能冻结其占位。其余安装位置、接头空间、散热及线束固定需实物核对。 |
| 采购完整度 | 部件类别与功能分工基本齐全；IMU和线束的具体商品暂不继续搜索，不能称作已完整验证的下单清单。 |

**阶段结论：保留CS30＋ZERO 3W、IMU的硬件组成。部件用途已明确，暂未发现要求推翻架构的硬性冲突；这不等于整机已经验证无误。下一步硬件讨论集中于连接关系和结构安排，不展开固件，不因尚未装机而继续泛搜更多器件。**

## 六、接入时保留的验证项

- **实现路径：** 已下载并静态检查ARMv8 SDK 4.2.5.0，资料见 `glasses_refs/cs30_radxa/`；尚未在Radxa＋CS30实物运行。当前只记录有支持路径，不指定软件版本组合、采集参数或编码实现。
- **联合工作：** 相机持续出帧、IMU及无线通信需同时测试；单项能工作不代表整机通过。
- **结构与佩戴：** 已有CS30和Radxa官方STP；小模块、接头与线束高度按实物确认，并验证装壳后的散热和无线效果。相机与IMU保持刚性安装关系。

## 七、器件与采购参考（具体商品暂不继续搜索）

| 器件 | 数量 | 型号 | 在哪买 / 怎么搜 |
|---|---:|---|---|
| 深度＋彩色相机 | 1 | Synexens CS30（DFRobot SEN0673） | DFRobot；淘宝搜“Synexens CS30” |
| 主板 | 1 | Radxa ZERO 3W，2GB＋16GB eMMC，已焊排针，另核实双频无线版本 | [ARACE](https://arace.tech/products/radxa-zero-3w)；原SKU RS107-D2E16H1W15仅作候选信息 |
| 散热片 | 1 | Radxa Heatsink 5519A | ARACE 同店 |
| 成品电源及内部分电件 | 待定 | 单Type-C 5V输入，优先5V/3A；NB10000 Gen4、PB40 mini等作候选，详见第四节 | 成品/OEM，不自行制作电池组；购买与代工链接已保留，尚未定型 |
| 相机USB转接板 | 候选1 | 8086 Consultancy USB-C/PWR Splitter，不带圆口座 | [Lectronz](https://lectronz.com/products/usb-c_pwr-splitter)，待整体连接方案确认 |
| USB线 | 待定 | 支持USB2.0数据；接头、长度和数量随分电方案确定 | 成品短线/弯头线，核实可传数据 |
| IMU | 1 | ICM-42688-P成品板；Qwiic方案已查，具体商品暂不定 | [LogicalEdges参考板](https://www.elecrow.com/icm-42688-p-ultra-low-power-imu-breakout.html)，不锁定为必购 |
| IMU连接线 | 1 | 若选Qwiic板，可用Adafruit 4397（150mm） | 随实际模块接口配套 |
| 外接天线 | 1（可选） | Taoglas FXP830.07.0100C | 立创/Mouser |
| 耗材 | 若干 | M2 螺丝 | 淘宝 |

## 主要来源

- [CS30 手册：尺寸、重量、分辨率、功耗](https://dfimg.dfrobot.com/wiki/17502/SEN0673_rgbd-depth-camera_datasheet_V1.0.pdf)；[CS30 视场与测距范围](https://support.tofsensors.com/product/CS30.html)；[CS30 产品与 ARM 开发板供电说明](https://tofsensors.com/products/rgbd-3d-camera)
- [Synexens SDK 4.2.5.0 使用说明](https://support.tofsensors.com/sdk/4.2.5.0/docs/CN/SynexensSDK4_Instructions_for_use_v2.0-CN.pdf)
- [Radxa ZERO 3W 产品简介（SKU、主机口500mA）](https://dl.radxa.com/zero3/docs/hw/3w/radxa_zero_3w_product_brief.pdf)；[版本与无线说明](https://docs.radxa.com/zero/zero3/faq)；[Radxa官方40针接口表](https://docs.radxa.com/zero/zero3/hardware-design/hardware-interface)
- [RK3568系列引脚复用定义](https://github.com/torvalds/linux/blob/master/arch/arm64/boot/dts/rockchip/rk3568-pinctrl.dtsi)；[Radxa I2C4-M0 overlay](https://github.com/radxa-pkg/radxa-overlays/blob/main/arch/arm64/boot/dts/rockchip/overlays/rk3568-i2c4-m0.dts)。Radxa参考配置本地副本：`glasses_refs/cs30_radxa/radxa_zero3_reference.dtsi`。
- [WOAD论文：相机、ARM/FPGA分工与反馈硬件](https://www.nature.com/articles/s41467-025-58085-x)
- [8086 USB-C/PWR Splitter 接线表](https://lectronz.com/products/usb-c_pwr-splitter)
- [ICM-42688-P Qwiic 小板](https://www.elecrow.com/icm-42688-p-ultra-low-power-imu-breakout.html)；[Adafruit 4397](https://www.adafruit.com/product/4397)
