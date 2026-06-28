package com.weldingdefect

import android.content.Context

class AuthStorage(context: Context) {
    private val prefs = context.getSharedPreferences("auth", Context.MODE_PRIVATE)

    var baseUrl: String
        get() = prefs.getString(KEY_BASE_URL, DEFAULT_BASE_URL) ?: DEFAULT_BASE_URL
        set(value) = prefs.edit().putString(KEY_BASE_URL, normalizeBaseUrl(value)).apply()

    var accessToken: String?
        get() = prefs.getString(KEY_ACCESS_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_ACCESS_TOKEN, value).apply()

    var refreshToken: String?
        get() = prefs.getString(KEY_REFRESH_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_REFRESH_TOKEN, value).apply()

    var username: String
        get() = prefs.getString(KEY_USERNAME, "") ?: ""
        set(value) = prefs.edit().putString(KEY_USERNAME, value).apply()

    var displayName: String
        get() = prefs.getString(KEY_DISPLAY_NAME, "") ?: ""
        set(value) = prefs.edit().putString(KEY_DISPLAY_NAME, value).apply()

    fun isLoggedIn(): Boolean = !accessToken.isNullOrBlank() && baseUrl.isNotBlank()

    fun saveLogin(baseUrl: String, username: String, tokens: AuthTokens, profile: UserProfile?) {
        prefs.edit()
            .putString(KEY_BASE_URL, normalizeBaseUrl(baseUrl))
            .putString(KEY_USERNAME, username)
            .putString(KEY_ACCESS_TOKEN, tokens.access)
            .putString(KEY_REFRESH_TOKEN, tokens.refresh)
            .putString(KEY_DISPLAY_NAME, profile?.fullName.orEmpty())
            .apply()
    }

    fun clear() {
        prefs.edit()
            .remove(KEY_ACCESS_TOKEN)
            .remove(KEY_REFRESH_TOKEN)
            .remove(KEY_USERNAME)
            .remove(KEY_DISPLAY_NAME)
            .apply()
    }

    companion object {
        const val DEFAULT_BASE_URL = "http://192.168.0.104:8000/"
        private const val KEY_BASE_URL = "base_url"
        private const val KEY_ACCESS_TOKEN = "access_token"
        private const val KEY_REFRESH_TOKEN = "refresh_token"
        private const val KEY_USERNAME = "username"
        private const val KEY_DISPLAY_NAME = "display_name"

        fun normalizeBaseUrl(value: String): String {
            val trimmed = value.trim()
            val withScheme = if (trimmed.startsWith("http://") || trimmed.startsWith("https://")) {
                trimmed
            } else {
                "http://$trimmed"
            }
            return if (withScheme.endsWith("/")) withScheme else "$withScheme/"
        }
    }
}
