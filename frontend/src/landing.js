let isLoginMode = true;

document.getElementById('toggle-mode').addEventListener('click', () => {
  isLoginMode = !isLoginMode;
  document.getElementById('auth-title').innerText = isLoginMode ? 'Sign In' : 'Create Account';
  document.getElementById('submit-btn').innerText = isLoginMode ? 'Login' : 'Register';
  document.querySelector('.auth-toggle').innerHTML = isLoginMode 
    ? "Don't have an account? <span>Register here</span>" 
    : "Already have an account? <span>Login here</span>";
  document.getElementById('error-msg').innerText = '';
});

document.getElementById('auth-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  
  const username = document.getElementById('username').value;
  const password = document.getElementById('password').value;
  const endpoint = isLoginMode ? '/api/login' : '/api/register';

  try {
    const res = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const data = await res.json();

    if (data.success) {
      window.location.href = '/index.html'; // Redirect to main navigation app
    } else {
      document.getElementById('error-msg').innerText = data.message || 'Authentication failed.';
    }
  } catch (err) {
    document.getElementById('error-msg').innerText = 'Network error occurred.';
  }
});