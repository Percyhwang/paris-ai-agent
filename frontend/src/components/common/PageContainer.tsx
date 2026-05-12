type PageContainerProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
  theme?: "places" | "trip" | "reservation" | "budget" | "diary" | "weather";
  children: React.ReactNode;
};

export function PageContainer({ eyebrow, title, description, action, theme = "trip", children }: PageContainerProps) {
  return (
    <main className="page-shell">
      <header className={`page-header page-header-${theme}`}>
        <div className="page-header-mark" aria-hidden="true" />
        <div className="page-header-copy">
          {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
          <h1>{title}</h1>
          {description ? <p>{description}</p> : null}
        </div>
        {action ? <div className="page-action">{action}</div> : null}
      </header>
      {children}
    </main>
  );
}
