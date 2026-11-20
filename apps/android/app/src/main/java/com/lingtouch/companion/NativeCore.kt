package com.lingtouch.companion

/** C++ 核心的 JNI 入口（app/src/main/cpp/jni_bridge.cpp）。所有取流、拆帧、栅格、编码都在核心里。 */
object NativeCore {
    init {
        System.loadLibrary("lingtouch_jni")  // 依赖的 libusb-1.0.so 由动态链接器一起加载
    }

    /** 0 表示失败，原因见 [nativeCreateError]。 */
    @JvmStatic external fun nativeCreate(): Long
    @JvmStatic external fun nativeCreateError(): String
    @JvmStatic external fun nativeDestroy(handle: Long)

    /** 只在采集工作线程调用；系统 USB 操作回调到 host，连接由原生层通知 host 关闭。 */
    @JvmStatic external fun nativeOpenCamera(handle: Long, host: StreamService, deviceId: String, withColor: Boolean): String?
    @JvmStatic external fun nativeCloseCamera(handle: Long)
    /** 最近的取流日志（含 libusb 自己的告警）。 */
    @JvmStatic external fun nativeUsbLog(): String
    @JvmStatic external fun nativeResetCamera(handle: Long): String?
    @JvmStatic external fun nativeCameraStreaming(handle: Long): Boolean
    @JvmStatic external fun nativeCameraStatus(handle: Long): String
    @JvmStatic external fun nativeCameraCode(handle: Long): Int
    @JvmStatic external fun nativeCameraEpoch(handle: Long): Long
    @JvmStatic external fun nativeCameraPreview(handle: Long, afterFrameId: Long): CameraPreviewFrame?

    @JvmStatic external fun nativeGridJson(handle: Long): String
    @JvmStatic external fun nativeStatsJson(handle: Long): String
    @JvmStatic external fun nativeDeviceSummary(handle: Long): String
    @JvmStatic external fun nativeConfigText(handle: Long): String

    /** 0 = 配置里没设定（待 Hsinlung 定），1 = 平，2 = 凸。 */
    @JvmStatic external fun nativeConfigUnknownPolicy(handle: Long): Int

    /** 最新栅格 → 15 字节旧板帧；policy 必须是 1 或 2。失败返回 null，原因见 [nativeLastError]。 */
    @JvmStatic external fun nativeEncodeLatest(handle: Long, policy: Int): ByteArray?
    @JvmStatic external fun nativeLastError(handle: Long): String

    @JvmStatic external fun nativePlaneCheck(handle: Long): String

    /** 真机验收：存最近一帧原始深度（返回 null 表示成功）；对帧文件算栅格（返回栅格 JSON，含 digest）。 */
    @JvmStatic external fun nativeSaveLatestFrame(handle: Long, path: String): String?
    @JvmStatic external fun nativeProcessFrameFile(handle: Long, path: String): String

    @JvmStatic external fun nativeImuTimeNs(): Long
    @JvmStatic external fun nativeStartImu(handle: Long): String?
    @JvmStatic external fun nativeStopImu(handle: Long)
    @JvmStatic external fun nativePushImuNotify(handle: Long, data: ByteArray, receivedNs: Long)
    @JvmStatic external fun nativeLatestImu(handle: Long): String

    const val POLICY_UNSET = 0
    const val POLICY_FLAT = 1
    const val POLICY_RAISED = 2
    // Values match CameraCode in core/include/lingtouch/modules.h.
    const val CAMERA_OPEN_FAILED = 3
    const val CAMERA_START_FAILED = 5
    const val CAMERA_DISCONNECTED = 8
    const val CAMERA_INTERRUPTED = 9
    const val CAMERA_IO_ERROR = 11
}
