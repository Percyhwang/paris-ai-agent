export function LoadingState({ label = "불러오는 중입니다" }: { label?: string }) {
  return (
    <div className="loading-state">
      <div className="loader" />
      <span>{label}</span>
    </div>
  );
}
