import Foundation

enum APIError: LocalizedError {
    case noServerURL
    case noToken
    case unauthorized
    case notFound
    case serverError(Int, String?)
    case networkError(Error)
    case decodingError(Error)
    case offline

    var errorDescription: String? {
        switch self {
        case .noServerURL: return "Server URL not configured"
        case .noToken: return "Not authenticated"
        case .unauthorized: return "Session expired. Please log in again."
        case .notFound: return "Not found"
        case .serverError(let code, let msg): return "Server error \(code): \(msg ?? "")"
        case .networkError(let err): return "Network error: \(err.localizedDescription)"
        case .decodingError(let err): return "Decoding error: \(err.localizedDescription)"
        case .offline: return "No internet connection"
        }
    }
}

actor APIClient {
    static let shared = APIClient()

    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 30
        config.timeoutIntervalForResource = 120
        session = URLSession(configuration: config)

        decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let container = try decoder.singleValueContainer()
            let string = try container.decode(String.self)
            // Try ISO 8601 with fractional seconds
            let formatters: [ISO8601DateFormatter] = {
                let f1 = ISO8601DateFormatter()
                f1.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                let f2 = ISO8601DateFormatter()
                f2.formatOptions = [.withInternetDateTime]
                return [f1, f2]
            }()
            for formatter in formatters {
                if let date = formatter.date(from: string) { return date }
            }
            // Try date-only
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "yyyy-MM-dd"
            if let date = dateFormatter.date(from: string) { return date }
            // Try time-only
            dateFormatter.dateFormat = "HH:mm:ss"
            if let date = dateFormatter.date(from: string) { return date }
            dateFormatter.dateFormat = "HH:mm"
            if let date = dateFormatter.date(from: string) { return date }
            throw DecodingError.dataCorruptedError(in: container, debugDescription: "Cannot decode date: \(string)")
        }

        encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
    }

    // MARK: - Core request method (body pre-encoded to Data)

    private func performRequest<T: Decodable>(
        path: String,
        method: String,
        bodyData: Data?,
        requiresAuth: Bool
    ) async throws -> T {
        guard let baseURL = await AuthManager.shared.serverURL else {
            throw APIError.noServerURL
        }

        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIError.noServerURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue("application/json", forHTTPHeaderField: "Accept")

        if requiresAuth {
            guard let token = await AuthManager.shared.accessToken else {
                throw APIError.noToken
            }
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        request.httpBody = bodyData

        let data: Data
        let response: URLResponse
        do {
            (data, response) = try await session.data(for: request)
        } catch {
            throw APIError.networkError(error)
        }

        guard let httpResponse = response as? HTTPURLResponse else {
            throw APIError.networkError(URLError(.badServerResponse))
        }

        switch httpResponse.statusCode {
        case 200...299:
            break
        case 401:
            if requiresAuth {
                let refreshed: T = try await refreshAndRetry(
                    path: path, method: method, bodyData: bodyData
                )
                return refreshed
            }
            throw APIError.unauthorized
        case 404:
            throw APIError.notFound
        default:
            let message = String(data: data, encoding: .utf8)
            throw APIError.serverError(httpResponse.statusCode, message)
        }

        do {
            return try decoder.decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    // MARK: - Public request methods

    func request<T: Decodable>(
        path: String,
        method: String = "GET",
        requiresAuth: Bool = true
    ) async throws -> T {
        try await performRequest(path: path, method: method, bodyData: nil, requiresAuth: requiresAuth)
    }

    func request<T: Decodable, B: Encodable>(
        path: String,
        method: String = "GET",
        body: B,
        requiresAuth: Bool = true
    ) async throws -> T {
        let bodyData = try encoder.encode(body)
        return try await performRequest(path: path, method: method, bodyData: bodyData, requiresAuth: requiresAuth)
    }

    // MARK: - Non-generic request (for fire-and-forget)

    func requestRaw<B: Encodable>(
        path: String,
        method: String = "GET",
        body: B
    ) async throws -> Data {
        guard let baseURL = await AuthManager.shared.serverURL else {
            throw APIError.noServerURL
        }

        guard let url = URL(string: path, relativeTo: baseURL) else {
            throw APIError.noServerURL
        }

        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = await AuthManager.shared.accessToken {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        request.httpBody = try encoder.encode(body)

        let (data, _) = try await session.data(for: request)
        return data
    }

    // MARK: - Token refresh

    private struct RefreshRequest: Encodable {
        let refreshToken: String
    }
    private struct RefreshResponse: Decodable {
        let accessToken: String
        let refreshToken: String
    }

    private func refreshAndRetry<T: Decodable>(
        path: String,
        method: String,
        bodyData: Data?
    ) async throws -> T {
        guard let refreshToken = await AuthManager.shared.refreshToken else {
            throw APIError.unauthorized
        }

        let refreshResponse: RefreshResponse = try await request(
            path: "/api/v1/auth/refresh",
            method: "POST",
            body: RefreshRequest(refreshToken: refreshToken),
            requiresAuth: false
        )

        await AuthManager.shared.storeTokens(
            access: refreshResponse.accessToken,
            refresh: refreshResponse.refreshToken
        )

        // Retry original request with pre-encoded body
        return try await performRequest(
            path: path, method: method, bodyData: bodyData, requiresAuth: true
        )
    }

    // MARK: - Auth

    func login(username: String, password: String, serverURL: URL, clientId: String) async throws {
        await AuthManager.shared.setServerURL(serverURL)

        struct LoginRequest: Encodable {
            let username: String
            let password: String
            let clientId: String
        }
        struct LoginResponse: Decodable {
            let accessToken: String
            let refreshToken: String
        }

        let response: LoginResponse = try await request(
            path: "/api/v1/auth/token",
            method: "POST",
            body: LoginRequest(username: username, password: password, clientId: clientId),
            requiresAuth: false
        )

        await AuthManager.shared.storeTokens(
            access: response.accessToken,
            refresh: response.refreshToken
        )
    }
}
