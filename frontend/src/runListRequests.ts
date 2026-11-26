// Keep one background refresh pending; explicit refresh/view changes may replace it.
export class RunListRequests {
  private epoch = 0;
  private pending = false;
  start(force = true): number | null {
    if (this.pending && !force) return null;
    this.pending = true;
    return ++this.epoch;
  }
  accepts(ticket: number) {
    return ticket === this.epoch;
  }
  finish(ticket: number) {
    if (!this.accepts(ticket)) return false;
    this.pending = false;
    return true;
  }
  invalidate() {
    this.epoch += 1;
    this.pending = false;
  }
}
