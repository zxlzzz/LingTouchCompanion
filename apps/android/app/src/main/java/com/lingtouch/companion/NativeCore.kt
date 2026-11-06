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

    /** fd 来自 UsbDeviceConnection.getFileDescriptor()，由调用方在 [nativeCloseCamera] 之后关闭。返回 null 表示成功。 */
    @JvmStatic external fun nativeOpenCamera(handle: Long, fd: Int): String?
    @JvmStatic external fun nativeCloseCamera(handle: Long)
    /** 最近的取流日志（含 libusb 自己的告警）。 */
    @JvmStatic external fun nativeUsbLog(): String
    @JvmStatic external fun nativeResetCamera(handle: Long): String?
    @JvmStatic external fun nativeCameraStreaming(handle: Long): Boolean

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

    const val POLICY_UNSET = 0
    const val POLICY_FLAT = 1
    const val POLICY_RAISED = 2
}
