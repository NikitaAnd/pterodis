import Foundation

struct VlessConfig: Codable, Equatable {
    let uuid: String
    let host: String
    let port: Int
    let flow: String?
    let security: String
    let type: String
    let sni: String?
    let publicKey: String?
    let shortId: String?
    let path: String?
    let remark: String
}

enum VlessParseError: LocalizedError {
    case invalidScheme
    case missingCredentials
    case missingHost
    case missingPort

    var errorDescription: String? {
        switch self {
        case .invalidScheme:
            return "Ссылка должна начинаться с vless://"
        case .missingCredentials:
            return "Не найден UUID пользователя"
        case .missingHost:
            return "Не найден сервер (host)"
        case .missingPort:
            return "Не найден порт"
        }
    }
}

extension VlessConfig {
    static func parse(from rawKey: String) throws -> VlessConfig {
        let trimmed = rawKey.trimmingCharacters(in: .whitespacesAndNewlines)
        guard trimmed.lowercased().hasPrefix("vless://") else {
            throw VlessParseError.invalidScheme
        }

        guard let components = URLComponents(string: trimmed) else {
            throw VlessParseError.invalidScheme
        }

        guard let uuid = components.user, !uuid.isEmpty else {
            throw VlessParseError.missingCredentials
        }

        guard let host = components.host, !host.isEmpty else {
            throw VlessParseError.missingHost
        }

        let port = components.port ?? 443
        if components.port == nil {
            throw VlessParseError.missingPort
        }

        let queryItems = Dictionary(uniqueKeysWithValues: (components.queryItems ?? []).map { ($0.name, $0.value ?? "") })

        return VlessConfig(
            uuid: uuid,
            host: host,
            port: port,
            flow: queryItems["flow"],
            security: queryItems["security", default: "reality"],
            type: queryItems["type", default: "tcp"],
            sni: queryItems["sni"],
            publicKey: queryItems["pbk"],
            shortId: queryItems["sid"],
            path: queryItems["path"],
            remark: components.fragment ?? host
        )
    }

    func asPrettyJSON() -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .withoutEscapingSlashes, .sortedKeys]

        guard let data = try? encoder.encode(self), let text = String(data: data, encoding: .utf8) else {
            return "{}"
        }

        return text
    }
}
