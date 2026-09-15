import SwiftUI

// MARK: - Design tokens derived from the web UI CSS variables (design-tokens.json)

enum Theme {

    // MARK: - Colors

    /// Primary brand blue – buttons, links, active states
    static let primary = Color(.primary)
    /// Muted text – secondary labels, metadata
    static let muted = Color(.muted)
    /// Section / summary label text
    static let summaryLabel = Color(.summaryLabel)
    /// Card / panel background
    static let panelBackground = Color(.panelBackground)
    /// Page-level background
    static let background = Color(.background)
    /// Navigation bar tint
    static let navBackground = Color(.navBackground)
    /// Danger / destructive actions
    static let danger = Color(.danger)
    /// Warning accent (flags, pending)
    static let warning = Color(.warning)
    /// Success accent
    static let success = Color(.success)
    /// Borders & dividers
    static let border = Color(.border)

    // MARK: - Typography

    enum Font {
        /// Small metadata – 11pt
        static func xs(_ weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: 11, weight: weight)
        }
        /// Secondary labels – 12pt
        static func sm(_ weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: 12, weight: weight)
        }
        /// Body / default – 14pt
        static func base(_ weight: SwiftUI.Font.Weight = .regular) -> SwiftUI.Font {
            .system(size: 14, weight: weight)
        }
        /// Subheadings – 16pt
        static func md(_ weight: SwiftUI.Font.Weight = .semibold) -> SwiftUI.Font {
            .system(size: 16, weight: weight)
        }
        /// Section headings – 18pt
        static func lg(_ weight: SwiftUI.Font.Weight = .semibold) -> SwiftUI.Font {
            .system(size: 18, weight: weight)
        }
        /// Large display (IATA codes) – 22pt
        static func xl(_ weight: SwiftUI.Font.Weight = .bold) -> SwiftUI.Font {
            .system(size: 22, weight: weight)
        }
        /// Hero display – 28pt
        static func xxl(_ weight: SwiftUI.Font.Weight = .bold) -> SwiftUI.Font {
            .system(size: 28, weight: weight)
        }
        /// Monospace for codes / technical values
        static func mono(_ size: CGFloat = 14) -> SwiftUI.Font {
            .system(size: size, design: .monospaced)
        }
    }

    // MARK: - Spacing

    enum Spacing {
        static let xxs: CGFloat = 2
        static let xs: CGFloat = 4
        static let sm: CGFloat = 8
        static let md: CGFloat = 12
        static let lg: CGFloat = 16
        static let xl: CGFloat = 20
        static let xxl: CGFloat = 24
        static let xxxl: CGFloat = 32
    }

    // MARK: - Corner Radius

    enum Radius {
        static let sm: CGFloat = 6
        static let md: CGFloat = 10
        static let lg: CGFloat = 12
        static let xl: CGFloat = 16
        static let pill: CGFloat = 999
    }
}

// MARK: - Adaptive UIColor definitions (light / dark pairs from CSS vars)

private extension UIColor {
    static let primary = UIColor { tc in
        tc.userInterfaceStyle == .dark
            ? UIColor(hex: 0x3B82F6)
            : UIColor(hex: 0x2563EB)
    }
    static let muted = UIColor { tc in
        tc.userInterfaceStyle == .dark
            ? UIColor(hex: 0x94A3B8)
            : UIColor(hex: 0x64748B)
    }
    static let summaryLabel = UIColor { tc in
        tc.userInterfaceStyle == .dark
            ? UIColor(hex: 0x94A3B8)
            : UIColor(hex: 0x475569)
    }
    static let panelBackground = UIColor { tc in
        tc.userInterfaceStyle == .dark
            ? UIColor(hex: 0x131C2F)
            : UIColor(hex: 0xFFFFFF)
    }
    static let background = UIColor { tc in
        tc.userInterfaceStyle == .dark
            ? UIColor(hex: 0x0F172A)
            : UIColor(hex: 0xF6F7FB)
    }
    static let navBackground = UIColor { tc in
        tc.userInterfaceStyle == .dark
            ? UIColor(hex: 0x0B1220)
            : UIColor(hex: 0x1E293B)
    }
    static let danger = UIColor { tc in
        tc.userInterfaceStyle == .dark
            ? UIColor(hex: 0xF87171)
            : UIColor(hex: 0xDC2626)
    }
    static let warning = UIColor { tc in
        tc.userInterfaceStyle == .dark
            ? UIColor(hex: 0xFDE68A)
            : UIColor(hex: 0x92400E)
    }
    static let success = UIColor { tc in
        tc.userInterfaceStyle == .dark
            ? UIColor(hex: 0xA7F3D0)
            : UIColor(hex: 0x166534)
    }
    static let border = UIColor { tc in
        tc.userInterfaceStyle == .dark
            ? UIColor(hex: 0x1F2937)
            : UIColor(hex: 0xE2E8F0)
    }

    convenience init(hex: UInt, alpha: CGFloat = 1) {
        self.init(
            red: CGFloat((hex >> 16) & 0xFF) / 255,
            green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255,
            alpha: alpha
        )
    }
}

// MARK: - View modifiers for consistent panel styling

extension View {
    /// Standard card / panel style matching the web UI panels.
    func panelStyle() -> some View {
        self
            .padding(Theme.Spacing.lg)
            .background(Theme.panelBackground)
            .clipShape(RoundedRectangle(cornerRadius: Theme.Radius.lg))
            .overlay(
                RoundedRectangle(cornerRadius: Theme.Radius.lg)
                    .stroke(Theme.border.opacity(0.5), lineWidth: 1)
            )
    }
}
