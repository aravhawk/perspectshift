type EmptyStateProps = {
  title: string;
  children: React.ReactNode;
};

export function EmptyState({ title, children }: EmptyStateProps) {
  return (
    <section className="empty-state" role="status" aria-live="polite">
      <h2>{title}</h2>
      <div>{children}</div>
    </section>
  );
}
