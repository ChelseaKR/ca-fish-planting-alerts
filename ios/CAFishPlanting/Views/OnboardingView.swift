import SwiftUI
import PlantingCore

/// The introduction: four pages on a first launch, swiped or stepped through
/// with Continue, skippable from the first page. The words are
/// `OnboardingCopy`, where a test holds them to the app's rules.
///
/// It asks for nothing. Notification permission stays where it was, behind
/// the first favorite's own explanation (`NotificationPrimingView`), so a
/// reviewer or a new angler is never asked before they know what for.
struct OnboardingView: View {
    let finish: () -> Void

    @State private var selection = OnboardingCopy.pages[0].id
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private let pages = OnboardingCopy.pages
    private var index: Int { pages.firstIndex { $0.id == selection } ?? 0 }
    private var isLast: Bool { index == pages.count - 1 }

    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Spacer()
                // Not on the last page, where the main button already ends it.
                Button("Skip", action: finish)
                    .opacity(isLast ? 0 : 1)
                    .disabled(isLast)
                    .accessibilityHidden(isLast)
                    .accessibilityHint("Closes the introduction")
            }
            .padding(.horizontal)
            .padding(.top, 8)

            TabView(selection: $selection) {
                ForEach(Array(pages.enumerated()), id: \.element.id) { offset, page in
                    OnboardingPageView(page: page, number: offset + 1, count: pages.count, isCurrent: page.id == selection)
                        .tag(page.id)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .always))
            .indexViewStyle(.page(backgroundDisplayMode: .always))

            Button {
                if isLast {
                    finish()
                } else if reduceMotion {
                    selection = pages[index + 1].id
                } else {
                    withAnimation(.snappy) { selection = pages[index + 1].id }
                }
            } label: {
                Text(isLast ? "Start browsing" : "Continue")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
            .accessibilityHint(isLast ? "Closes the introduction" : "Page \(index + 2) of \(pages.count)")
            .padding()
        }
        .background(OnboardingBackground())
        // A light tick for each page, swiped or stepped. iOS skips it when
        // system haptics are off.
        .sensoryFeedback(.selection, trigger: selection)
    }
}

/// One page: a symbol in a tinted disc, a title, a sentence and its points.
/// It scrolls, so at the largest text sizes nothing is cut off and the page
/// dots never cover a word.
private struct OnboardingPageView: View {
    let page: OnboardingCopy.Page
    let number: Int
    let count: Int
    let isCurrent: Bool

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ScaledMetric(relativeTo: .largeTitle) private var discSize: CGFloat = 112

    var body: some View {
        ScrollView {
            VStack(spacing: 24) {
                symbol
                    .padding(.top, dynamicTypeSize.isAccessibilitySize ? 8 : 32)

                VStack(spacing: 12) {
                    Text(page.title)
                        .font(.largeTitle.bold())
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                        .accessibilityLabel("\(page.title), page \(number) of \(count)")
                    Text(page.body)
                        .font(.title3)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }

                VStack(alignment: .leading, spacing: 14) {
                    ForEach(page.points, id: \.self) { point in
                        Label {
                            Text(point)
                                .fixedSize(horizontal: false, vertical: true)
                        } icon: {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(.tint)
                                .accessibilityHidden(true)
                        }
                        .font(.body)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding()
                .background(.background.secondary, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            }
            .padding(.horizontal, 24)
            // Room for the page dots under the last line.
            .padding(.bottom, 56)
            .frame(maxWidth: 560)
            .frame(maxWidth: .infinity)
        }
        .scrollBounceBehavior(.basedOnSize)
    }

    private var symbol: some View {
        let size = min(discSize, dynamicTypeSize.isAccessibilitySize ? 96 : 160)
        return Image(systemName: page.systemImage)
            .font(.system(size: size * 0.42, weight: .semibold))
            .foregroundStyle(.white)
            .symbolEffect(.bounce, options: .nonRepeating, value: reduceMotion ? false : isCurrent)
            .frame(width: size, height: size)
            .background(Circle().fill(Color.accentColor.gradient))
            .shadow(color: Color.accentColor.opacity(0.35), radius: 16, y: 8)
            .accessibilityHidden(true)
    }
}

/// The accent color washing down from the top into the system background,
/// in light and dark mode.
private struct OnboardingBackground: View {
    var body: some View {
        LinearGradient(colors: [Color.accentColor.opacity(0.22), Color(uiColor: .systemBackground)],
                       startPoint: .top, endPoint: .center)
            .background(Color(uiColor: .systemBackground))
            .ignoresSafeArea()
    }
}
