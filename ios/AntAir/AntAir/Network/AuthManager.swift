import Foundation
import Security

actor AuthManager {
    static let shared = AuthManager()

    private let keychainService = "ai.antcodelabs.antair.api"
    private let accessTokenKey = "access_token"
    private let refreshTokenKey = "refresh_token"
    private let serverUrlKey = "server_url"

    nonisolated var hasValidToken: Bool {
        let token = readKeychain(key: accessTokenKey)
        return token != nil && !token!.isEmpty
    }

    var serverURL: URL? {
        get {
            guard let urlString = UserDefaults.standard.string(forKey: serverUrlKey) else {
                return nil
            }
            return URL(string: urlString)
        }
    }

    func setServerURL(_ url: URL) {
        UserDefaults.standard.set(url.absoluteString, forKey: serverUrlKey)
    }

    var accessToken: String? {
        readKeychain(key: accessTokenKey)
    }

    var refreshToken: String? {
        readKeychain(key: refreshTokenKey)
    }

    func storeTokens(access: String, refresh: String) {
        writeKeychain(key: accessTokenKey, value: access)
        writeKeychain(key: refreshTokenKey, value: refresh)
    }

    func clearTokens() {
        deleteKeychain(key: accessTokenKey)
        deleteKeychain(key: refreshTokenKey)
    }

    // MARK: - Keychain helpers

    private nonisolated func readKeychain(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        guard status == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    private func writeKeychain(key: String, value: String) {
        deleteKeychain(key: key)
        guard let data = value.data(using: .utf8) else { return }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: key,
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
        ]
        SecItemAdd(query as CFDictionary, nil)
    }

    private nonisolated func deleteKeychain(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: key,
        ]
        SecItemDelete(query as CFDictionary)
    }
}
