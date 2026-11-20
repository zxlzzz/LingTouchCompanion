plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.lingtouch.companion"
    compileSdk = 35
    ndkVersion = "27.0.12077973"

    defaultConfig {
        applicationId = "com.lingtouch.companion"
        minSdk = 29  // startForeground(id, notification, type) 需要 API 29
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
        externalNativeBuild {
            cmake {
                arguments += "-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON"
            }
        }
        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    // 核心（core/、perception/native/、agent/native/）和 libusb 由这份 CMake 一起编进来
    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.22.1"
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}
