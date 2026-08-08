/**
 * AsyncStorage Mock for Testing
 */

let storage = {};

export default {
  getItem: jest.fn((key) => {
    return Promise.resolve(storage[key]);
  }),
  
  setItem: jest.fn((key, value) => {
    storage[key] = value;
    return Promise.resolve();
  }),
  
  removeItem: jest.fn((key) => {
    delete storage[key];
    return Promise.resolve();
  }),
  
  clear: jest.fn(() => {
    storage = {};
    return Promise.resolve();
  }),
  
  multiGet: jest.fn(() => {
    const keys = Array.from(arguments);
    return Promise.resolve(keys.map((key) => [null, null]));
  }),
  
  multiSet: jest.fn(() => {
    return Promise.resolve();
  }),
  
  multiRemove: jest.fn(() => {
    return Promise.resolve();
  }),
};
