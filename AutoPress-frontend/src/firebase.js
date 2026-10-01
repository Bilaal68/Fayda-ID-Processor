import { initializeApp } from "firebase/app";
import {
  getAuth,
  createUserWithEmailAndPassword,
  signInWithEmailAndPassword,
  signOut,
  sendEmailVerification,
  sendPasswordResetEmail,
  updateProfile,
  onAuthStateChanged,
  setPersistence,
  browserLocalPersistence
} from "firebase/auth";

// Public Firebase web configuration
const firebaseConfig = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY || "AIzaSyChtSfuzgzbYK0FfxZXcmwleNMkp5OXe6s",
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN || "seer-95544.firebaseapp.com",
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID || "seer-95544",
  storageBucket: import.meta.env.VITE_FIREBASE_STORAGE_BUCKET || "seer-95544.firebasestorage.app",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "449833623014",
  appId: import.meta.env.VITE_FIREBASE_APP_ID || "1:449833623014:web:4c9a78c0972891f73a4a27",
  measurementId: import.meta.env.VITE_FIREBASE_MEASUREMENT_ID || "G-3HEWYSYX6N"
};

// Initialize Firebase App
export const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);

// Persist login permanently in localStorage (survives browser restart & refresh)
setPersistence(auth, browserLocalPersistence).catch(console.warn);

/**
 * Register with email and password, update profile name, and send email verification
 */
export async function firebaseRegister(email, password, fullName) {
  const userCredential = await createUserWithEmailAndPassword(auth, email, password);
  if (fullName && auth.currentUser) {
    try {
      await updateProfile(auth.currentUser, { displayName: fullName.trim() });
    } catch (e) {
      console.warn("Could not update displayName:", e);
    }
  }
  // Send email verification link directly from Firebase
  try {
    await sendEmailVerification(userCredential.user);
  } catch (err) {
    console.warn("Failed to send Firebase verification email:", err);
  }
  return userCredential.user;
}

/**
 * Sign in with email and password
 */
export async function firebaseLogin(email, password) {
  const userCredential = await signInWithEmailAndPassword(auth, email, password);
  return userCredential.user;
}

/**
 * Sign out current Firebase user
 */
export async function firebaseLogout() {
  await signOut(auth);
}

/**
 * Send password reset email via Firebase
 */
export async function firebaseSendPasswordReset(email) {
  await sendPasswordResetEmail(auth, email);
}

/**
 * Resend verification email to current user
 */
export async function firebaseResendVerification() {
  if (!auth.currentUser) throw new Error("No active user to send verification to.");
  await sendEmailVerification(auth.currentUser);
}

/**
 * Get the current fresh Firebase ID Token
 */
export async function getFreshIdToken(forceRefresh = false) {
  if (!auth.currentUser) return null;
  return await auth.currentUser.getIdToken(forceRefresh);
}

/**
 * Listen to auth state changes
 */
export function onAuthChange(callback) {
  return onAuthStateChanged(auth, callback);
}

// Expose on window for easy access in index.html if needed
if (typeof window !== "undefined") {
  window.FirebaseService = {
    auth,
    firebaseRegister,
    firebaseLogin,
    firebaseLogout,
    firebaseSendPasswordReset,
    firebaseResendVerification,
    getFreshIdToken,
    onAuthChange
  };
}
