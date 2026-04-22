import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import '../styles/Register.css';

const Register = () => {
  const [userData, setUserData] = useState({ 
    username: '', 
    email: '',
    password: '', 
    confirmPassword: '',
    website_url: ''
  });
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [passwordStrength, setPasswordStrength] = useState({
    hasMinLength: false,
    hasUpperCase: false,
    hasLowerCase: false,
    hasNumber: false,
    hasSpecialChar: false
  });
  const [passwordsMatch, setPasswordsMatch] = useState(true);
  const [emailValid, setEmailValid] = useState(true);
  const navigate = useNavigate();

  // Validate password strength in real-time
  useEffect(() => {
    const password = userData.password;
    setPasswordStrength({
      hasMinLength: password.length >= 8,
      hasUpperCase: /[A-Z]/.test(password),
      hasLowerCase: /[a-z]/.test(password),
      hasNumber: /[0-9]/.test(password),
      hasSpecialChar: /[!@#$%^&*()_+\-=[\]{}|;:,.<>?]/.test(password)
    });
  }, [userData.password]);

  // Check if passwords match
  useEffect(() => {
    if (userData.confirmPassword) {
      setPasswordsMatch(userData.password === userData.confirmPassword);
    } else {
      setPasswordsMatch(true);
    }
  }, [userData.password, userData.confirmPassword]);

  // Validate email format
  useEffect(() => {
    if (userData.email) {
      const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
      setEmailValid(emailRegex.test(userData.email));
    } else {
      setEmailValid(true);
    }
  }, [userData.email]);

  const handleChange = (e) => {
    const { name, value } = e.target;
    setUserData(prev => ({ ...prev, [name]: value }));
    setError('');
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    // Validate email
    if (!emailValid) {
      setError('Please enter a valid email address');
      return;
    }

    // Validate password strength
    const allPasswordRequirementsMet = Object.values(passwordStrength).every(val => val === true);
    if (!allPasswordRequirementsMet) {
      setError('Password does not meet all requirements');
      return;
    }
    
    // Validate passwords match
    if (userData.password !== userData.confirmPassword) {
      setError('Passwords do not match');
      return;
    }

    // Validate website URL
    if (!userData.website_url) {
      setError('Website URL is required');
      return;
    }

    const urlRegex = /^https?:\/\/[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}.*$/;
    if (!urlRegex.test(userData.website_url)) {
      setError('Please enter a valid URL (must start with http:// or https://)');
      return;
    }
    
    setIsLoading(true);
    setError('');
    setSuccess('');

    try {
      const response = await axios.post('https://chatboat-1-e4xt.onrender.com/register', {
        username: userData.username,
        email: userData.email,
        password: userData.password,
        website_url: userData.website_url
      });
      
      if (response.data.success) {
        setSuccess('Registration successful! Redirecting to login...');
        setTimeout(() => {
          navigate('/admin/login', { state: { registrationSuccess: true } });
        }, 2000);
      } else {
        setError(response.data.error || 'Registration failed');
      }
    } catch (error) {
      if (error.response && error.response.data && error.response.data.error) {
        setError(error.response.data.error);
      } else {
        setError('Registration failed. Please try again.');
      }
      console.error('Registration error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="register-container">
      <div className="register-card">
        <h2>Register New User</h2>
        
        {error && <div className="error-message">{error}</div>}
        {success && <div className="success-message" style={{backgroundColor: '#d4edda', color: '#155724', padding: '10px', borderRadius: '4px', marginBottom: '15px', border: '1px solid #c3e6cb'}}>{success}</div>}
        
        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              type="text"
              id="username"
              name="username"
              value={userData.username}
              onChange={handleChange}
              required
            />
          </div>
          
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              type="email"
              id="email"
              name="email"
              value={userData.email}
              onChange={handleChange}
              style={{borderColor: userData.email && !emailValid ? '#f44336' : ''}}
              required
            />
            {userData.email && !emailValid && (
              <div style={{color: '#f44336', fontSize: '12px', marginTop: '5px'}}>
                Please enter a valid email address
              </div>
            )}
          </div>
          
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              type="password"
              id="password"
              name="password"
              value={userData.password}
              onChange={handleChange}
              required
            />
            {userData.password && (
              <div className="password-requirements">
                <div className="password-requirements-title">Password Requirements</div>
                <div className={`password-requirement ${passwordStrength.hasMinLength ? 'valid' : 'invalid'}`}>
                  <span className="password-requirement-icon">{passwordStrength.hasMinLength ? '✓' : '✗'}</span>
                  <span>At least 8 characters</span>
                </div>
                <div className={`password-requirement ${passwordStrength.hasUpperCase ? 'valid' : 'invalid'}`}>
                  <span className="password-requirement-icon">{passwordStrength.hasUpperCase ? '✓' : '✗'}</span>
                  <span>One uppercase letter</span>
                </div>
                <div className={`password-requirement ${passwordStrength.hasLowerCase ? 'valid' : 'invalid'}`}>
                  <span className="password-requirement-icon">{passwordStrength.hasLowerCase ? '✓' : '✗'}</span>
                  <span>One lowercase letter</span>
                </div>
                <div className={`password-requirement ${passwordStrength.hasNumber ? 'valid' : 'invalid'}`}>
                  <span className="password-requirement-icon">{passwordStrength.hasNumber ? '✓' : '✗'}</span>
                  <span>One number</span>
                </div>
                <div className={`password-requirement ${passwordStrength.hasSpecialChar ? 'valid' : 'invalid'}`}>
                  <span className="password-requirement-icon">{passwordStrength.hasSpecialChar ? '✓' : '✗'}</span>
                  <span>One special character (!@#$%^&amp;*...)</span>
                </div>
              </div>
            )}
          </div>
          
          <div className="form-group">
            <label htmlFor="confirmPassword">Confirm Password</label>
            <input
              type="password"
              id="confirmPassword"
              name="confirmPassword"
              value={userData.confirmPassword}
              onChange={handleChange}
              style={{borderColor: userData.confirmPassword && !passwordsMatch ? '#f44336' : ''}}
              required
            />
            {userData.confirmPassword && !passwordsMatch && (
              <div style={{color: '#f44336', fontSize: '12px', marginTop: '5px'}}>
                Passwords do not match
              </div>
            )}
            {userData.confirmPassword && passwordsMatch && userData.confirmPassword.length > 0 && (
              <div style={{color: '#4CAF50', fontSize: '12px', marginTop: '5px'}}>
                ✓ Passwords match
              </div>
            )}
          </div>
          
          <div className="form-group">
            <label htmlFor="website_url">Website URL *</label>
            <input
              type="url"
              id="website_url"
              name="website_url"
              value={userData.website_url}
              onChange={handleChange}
              placeholder="https://example.com"
              required
            />
            <div className="helper-text">
              Enter your website URL (must start with http:// or https://)
            </div>
            <div className="website-warning-box">
              <span className="warning-icon">⚠️</span>
              <span className="warning-text">
                This URL determines where your chat widget will be authorized. Make sure to enter the exact domain where the widget should run.
              </span>
            </div>
          </div>
          
          <button 
            type="submit" 
            className="register-submit-button"
            disabled={isLoading}
          >
            {isLoading ? 'Registering...' : 'Register'}
          </button>
          
          <div className="login-link">
            <button 
              type="button" 
              className="back-to-login-button"
              onClick={() => navigate('/admin/login')}
            >
              Back to Login
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Register;