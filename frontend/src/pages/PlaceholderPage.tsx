import type { ReactNode } from "react";
import { Badge, Card } from "../components/ui/primitives";

interface PlaceholderPageProps {
  title: string;
  eyebrow: string;
  description: string;
  icon: ReactNode;
  endpoint: string;
}

function PageHeading({
  eyebrow,
  title,
  description,
  icon,
}: Omit<PlaceholderPageProps, "endpoint">) {
  return (
    <div className="page-heading animate-enter">
      <div>
        <div className="eyebrow">
          {icon}
          {eyebrow}
        </div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      <div className="heading-chip">
        <span className="status-dot status-violet" />
        Carbon-aware infrastructure
      </div>
    </div>
  );
}

export function PlaceholderPage({
  title,
  eyebrow,
  description,
  icon,
  endpoint,
}: PlaceholderPageProps) {
  return (
    <div className="page-stack">
      <PageHeading
        title={title}
        eyebrow={eyebrow}
        description={description}
        icon={icon}
      />
      <Card className="placeholder-card">
        <div className="placeholder-icon">{icon}</div>
        <Badge tone="violet">Stage 2 foundation</Badge>
        <h2>Ready for live feature integration</h2>
        <p>
          This page is intentionally a foundation placeholder. The next stage
          will connect the endpoint below and render its real loading, error,
          empty and success states.
        </p>
        <code>{endpoint}</code>
      </Card>
    </div>
  );
}