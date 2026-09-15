import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var appState: AppState
    @State private var serverURL = ""
    @State private var username = ""
    @State private var password = ""
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("Server URL", text: $serverURL)
                        .keyboardType(.URL)
                        .textContentType(.URL)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                }

                Section("Credentials") {
                    TextField("Username", text: $username)
                        .textContentType(.username)
                        .autocapitalization(.none)
                    SecureField("Password", text: $password)
                        .textContentType(.password)
                }

                if let error = errorMessage {
                    Section {
                        Text(error)
                            .foregroundStyle(Theme.danger)
                            .font(Theme.Font.sm())
                    }
                }

                Section {
                    Button(action: login) {
                        if isLoading {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Text("Sign In")
                                .font(Theme.Font.md(.semibold))
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .tint(Theme.primary)
                    .disabled(isLoading || serverURL.isEmpty || username.isEmpty || password.isEmpty)
                }
            }
            .background(Theme.background)
            .scrollContentBackground(.hidden)
            .navigationTitle("Ant Air")
        }
    }

    private func login() {
        guard let url = URL(string: serverURL) else {
            errorMessage = "Invalid server URL"
            return
        }

        isLoading = true
        errorMessage = nil

        let clientId = {
            if let stored = UserDefaults.standard.string(forKey: "device_client_id") {
                return stored
            }
            let id = UUID().uuidString
            UserDefaults.standard.set(id, forKey: "device_client_id")
            return id
        }()

        Task {
            do {
                try await APIClient.shared.login(
                    username: username,
                    password: password,
                    serverURL: url,
                    clientId: clientId
                )
                appState.isAuthenticated = true
            } catch {
                errorMessage = error.localizedDescription
            }
            isLoading = false
        }
    }
}
