import { Component, type ReactNode } from "react";
export class ProductBoundary extends Component<
  { children: ReactNode; onExit: () => void },
  { failed: boolean; attempt: number }
> {
  state = { failed: false, attempt: 0 };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed)
      return (
        <section className="panel" role="alert" style={{ padding: 28 }}>
          <h2>The UI workspace could not render</h2>
          <p>
            Your server accounts and project records were not changed. Retrying
            resets this local UI review session; exported handoff files remain
            available.
          </p>
          <div className="product-inline">
            <button
              className="btn btn-primary"
              onClick={() =>
                this.setState((s) => ({
                  failed: false,
                  attempt: s.attempt + 1,
                }))
              }
            >
              Retry UI workspace
            </button>
            <button className="btn btn-outline" onClick={this.props.onExit}>
              Return to command center
            </button>
          </div>
        </section>
      );
    return <div key={this.state.attempt}>{this.props.children}</div>;
  }
}
