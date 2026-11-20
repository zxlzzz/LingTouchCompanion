import java.util.Properties

plugins { id("com.android.application"); id("org.jetbrains.kotlin.android") }
val repository = rootProject.file("../..")
val generated = repository.resolve(".build/vision")
val localSettings = Properties().apply {
    val file = rootProject.file("local.properties")
    if (file.exists()) file.inputStream().use { load(it) }
}
android {
    namespace = "com.lingtouch.cs30live"
    compileSdk = 36
    ndkVersion = "27.2.12479018"
    (providers.gradleProperty("cs30NdkPath").orNull ?: localSettings.getProperty("cs30.ndk.path"))?.let { ndkPath = it }
    defaultConfig {
        applicationId = "com.lingtouch.cs30live"
        minSdk = 29
        targetSdk = 34
        versionCode = 3
        versionName = "1.2"
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
        testInstrumentationRunner = "com.lingtouch.cs30live.LiveCheck"
        externalNativeBuild { cmake {
            targets += listOf("cs30_live")
            // Keep the native pipeline optimized even in the installable debug APK.
            arguments += "-DCMAKE_BUILD_TYPE=Release"
            localSettings.getProperty("cs30.ninja.path")?.let { arguments += "-DCMAKE_MAKE_PROGRAM=$it" }
        } }
    }
    externalNativeBuild { cmake {
        path = rootProject.file("native/CMakeLists.txt")
        localSettings.getProperty("cs30.cmake.version")?.let { version = it }
    } }
    sourceSets.getByName("main").assets.srcDir(repository.resolve("vision/native/third_party/libusb/license_assets"))
    sourceSets.getByName("androidTest").jniLibs.srcDir(generated.resolve("test-jni"))
    sourceSets.getByName("androidTest").assets.srcDir(generated.resolve("test-assets"))
    compileOptions { sourceCompatibility = JavaVersion.VERSION_17; targetCompatibility = JavaVersion.VERSION_17 }
    kotlinOptions { jvmTarget = "17" }
    packaging { jniLibs.useLegacyPackaging = true }
    androidResources { noCompress += listOf("raw", "bin") }
}
