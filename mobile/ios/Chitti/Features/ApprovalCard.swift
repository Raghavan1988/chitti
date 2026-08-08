import SwiftUI

struct ApprovalCard: View {
    let item: ChatItem
    var onDecide: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Label("Approval needed", systemImage: "hand.raised.fill")
                .font(.subheadline.weight(.semibold))
            Text(item.text)
                .font(.body)
            if !item.resolved {
                HStack {
                    Button("Reject", role: .destructive) { onDecide(false) }
                        .buttonStyle(.bordered)
                    Button("Approve") { onDecide(true) }
                        .buttonStyle(.borderedProminent)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.12))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
