import { describe, it, expect } from 'vitest';
import { planDownload } from './download';

describe('planDownload', () => {
  it('saves the open file under its own name', () => {
    expect(planDownload('earthquake.pasp', false)).toEqual({
      filename: 'earthquake.pasp',
      needsFullFile: false
    });
  });

  it('asks for the whole file when the editor is showing a prefix', () => {
    // The subtle one. A file over MAX_EDITOR_LINES is open read-only and only
    // its first 1000 lines are in the buffer; saving that as the file would
    // hand the user a silently truncated copy of their own data.
    expect(planDownload('elmo.csv', true)).toEqual({
      filename: 'elmo.csv',
      needsFullFile: true
    });
  });

  it('has nothing to save when no file is open', () => {
    expect(planDownload('', false)).toBeNull();
    expect(planDownload('   ', false)).toBeNull();
  });
});
