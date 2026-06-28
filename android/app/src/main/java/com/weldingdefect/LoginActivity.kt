package com.weldingdefect

import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.core.view.WindowCompat
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputEditText
import java.io.IOException

class LoginActivity : AppCompatActivity() {
    private lateinit var storage: AuthStorage
    private val apiClient = ApiClient()

    private lateinit var etServerUrl: TextInputEditText
    private lateinit var etUsername: TextInputEditText
    private lateinit var etPassword: TextInputEditText
    private lateinit var btnLogin: MaterialButton
    private lateinit var tvStatus: TextView

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        configureSystemBars()
        storage = AuthStorage(this)

        if (storage.isLoggedIn()) {
            openMain()
            return
        }

        setContentView(R.layout.activity_login)
        etServerUrl = findViewById(R.id.etServerUrl)
        etUsername = findViewById(R.id.etUsername)
        etPassword = findViewById(R.id.etPassword)
        btnLogin = findViewById(R.id.btnLogin)
        tvStatus = findViewById(R.id.tvLoginStatus)

        etServerUrl.setText(storage.baseUrl)
        etUsername.setText(storage.username.ifBlank { "demo_worker" })

        btnLogin.setOnClickListener { login() }
    }

    private fun login() {
        val baseUrl = etServerUrl.text?.toString().orEmpty().trim()
        val username = etUsername.text?.toString().orEmpty().trim()
        val password = etPassword.text?.toString().orEmpty()

        if (baseUrl.isBlank() || username.isBlank() || password.isBlank()) {
            tvStatus.text = "Заполните адрес сервера, логин и пароль."
            return
        }

        setLoading(true)
        Thread {
            try {
                val tokens = apiClient.login(baseUrl, username, password)
                val profile = apiClient.me(baseUrl, tokens.access)
                storage.saveLogin(baseUrl, username, tokens, profile)
                runOnUiThread { openMain() }
            } catch (e: ApiHttpException) {
                runOnUiThread {
                    setLoading(false)
                    tvStatus.text = e.message ?: "Не удалось войти."
                }
            } catch (e: IOException) {
                runOnUiThread {
                    setLoading(false)
                    tvStatus.text = getString(R.string.login_first_online_required)
                }
            } catch (e: Exception) {
                runOnUiThread {
                    setLoading(false)
                    tvStatus.text = e.message ?: "Не удалось войти."
                }
            }
        }.start()
    }

    private fun setLoading(isLoading: Boolean) {
        btnLogin.isEnabled = !isLoading
        btnLogin.text = getString(if (isLoading) R.string.login_processing else R.string.login_action)
        etServerUrl.isEnabled = !isLoading
        etUsername.isEnabled = !isLoading
        etPassword.isEnabled = !isLoading
    }

    private fun openMain() {
        startActivity(Intent(this, MainActivity::class.java))
        finish()
    }

    private fun configureSystemBars() {
        window.statusBarColor = Color.rgb(246, 247, 249)
        window.navigationBarColor = Color.rgb(246, 247, 249)
        WindowCompat.getInsetsController(window, window.decorView).apply {
            isAppearanceLightStatusBars = true
            isAppearanceLightNavigationBars = true
        }
    }
}
