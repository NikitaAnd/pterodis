import SwiftUI

struct ContentView: View {
    @State private var keyInput = ""
    @State private var parsedConfig: VlessConfig?
    @State private var errorText: String?

    var body: some View {
        NavigationView {
            Form {
                Section("VLESS ключ") {
                    TextEditor(text: $keyInput)
                        .frame(minHeight: 110)
                        .font(.system(.body, design: .monospaced))

                    Button("Подключить") {
                        parseKey()
                    }
                    .buttonStyle(.borderedProminent)
                }

                if let errorText {
                    Section("Ошибка") {
                        Text(errorText)
                            .foregroundStyle(.red)
                    }
                }

                if let parsedConfig {
                    Section("Параметры") {
                        LabeledContent("Сервер", value: parsedConfig.host)
                        LabeledContent("Порт", value: String(parsedConfig.port))
                        LabeledContent("UUID", value: parsedConfig.uuid)
                        LabeledContent("Протокол", value: parsedConfig.type)
                        LabeledContent("Безопасность", value: parsedConfig.security)
                        if let sni = parsedConfig.sni, !sni.isEmpty {
                            LabeledContent("SNI", value: sni)
                        }
                    }

                    Section("JSON") {
                        ScrollView(.horizontal) {
                            Text(parsedConfig.asPrettyJSON())
                                .font(.system(.footnote, design: .monospaced))
                                .textSelection(.enabled)
                        }
                    }
                }
            }
            .navigationTitle("VLESS Connect")
        }
    }

    private func parseKey() {
        do {
            parsedConfig = try VlessConfig.parse(from: keyInput)
            errorText = nil
        } catch {
            parsedConfig = nil
            errorText = error.localizedDescription
        }
    }
}

#Preview {
    ContentView()
}
