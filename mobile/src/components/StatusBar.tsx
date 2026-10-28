export function StatusBar() {
  return (
    <div className="preview-status" aria-hidden="true">
      <span>9:41</span>
      <div className="status-icons">
        <span className="signal"><i /><i /><i /><i /></span>
        <span className="battery"><i /></span>
      </div>
    </div>
  )
}
