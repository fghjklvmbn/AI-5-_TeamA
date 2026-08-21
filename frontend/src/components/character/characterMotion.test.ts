import { characterMotionFor } from './characterMotion';

describe('characterMotionFor', () => {
  it('keeps a character stable without a cue', () => {
    expect(characterMotionFor(undefined, false, 1000)).toEqual({
      offsetX: 0, offsetY: 0, rotation: 0, scale: 1,
    });
  });

  it('bounds untrusted cue intensity', () => {
    const cue = { emotion: 'excited', intensity: 99, gesture: 'celebrate', voice_style: 'bright' } as const;
    const motion = characterMotionFor(cue, true, 700);
    expect(Math.abs(motion.offsetX)).toBeLessThanOrEqual(4);
    expect(Math.abs(motion.offsetY)).toBeLessThanOrEqual(8);
    expect(Math.abs(motion.rotation)).toBeLessThanOrEqual(0.025);
    expect(motion.scale).toBeLessThanOrEqual(1.012);
  });

  it('reduces motion while audio is not speaking', () => {
    const cue = { emotion: 'happy', intensity: 1, gesture: 'nod', voice_style: 'bright' } as const;
    const active = characterMotionFor(cue, true, 500);
    const resting = characterMotionFor(cue, false, 500);
    expect(Math.abs(resting.offsetY)).toBeLessThan(Math.abs(active.offsetY));
  });
});
