import { Component } from 'react';

/** Catches render errors in a page so the shell stays usable; `resetKey` (e.g. the route) clears it on navigation. */
export default class ErrorBoundary extends Component {
  state = { error: null, key: this.props.resetKey };
  static getDerivedStateFromError(error) { return { error }; }
  static getDerivedStateFromProps(props, state) {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null;
  }
  componentDidCatch(error) { console.error(error); }
  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="card error-boundary" role="alert">
        <h2>Something went wrong</h2>
        <p className="muted">{this.state.error.message || 'Unexpected error.'}</p>
        <button type="button" className="btn primary" onClick={() => this.setState({ error: null })}>Try again</button>
      </div>
    );
  }
}
