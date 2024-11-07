import { useState, useEffect } from 'react';
import config from '../../../config';

export const useStudentData = () => {
  const [students, setStudents] = useState([]);
  const [classes, setClasses] = useState([]);
  const [sections, setSections] = useState({});
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchStudents = async () => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/db/students`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setStudents(data);
      setError(null);
    } catch (error) {
      console.error('Error fetching students:', error);
      setError('Failed to load students. Please try again later.');
    } finally {
      setLoading(false);
    }
  };

  const fetchClasses = async () => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/db/classes`);
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      setClasses(data.classes);
      
      const sectionsMap = {};
      await Promise.all(data.classes.map(async (cls) => {
        const sectionsResponse = await fetch(`${config.apiBaseUrl}/db/classes/${cls.id}/sections`);
        if (sectionsResponse.ok) {
          const sectionsData = await sectionsResponse.json();
          sectionsMap[cls.id] = sectionsData.sections;
        }
      }));
      setSections(sectionsMap);
    } catch (error) {
      console.error('Error fetching classes:', error);
    }
  };

  const addSection = async (newSection) => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/db/sections`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newSection),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      await fetchClasses();
      return true;
    } catch (error) {
      console.error('Error adding section:', error);
      return false;
    }
  };

  const addStudent = async (newStudent) => {
    try {
      const response = await fetch(`${config.apiBaseUrl}/db/students`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(newStudent),
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      await fetchStudents();
      return true;
    } catch (error) {
      console.error('Error adding student:', error);
      return false;
    }
  };

  const filterStudents = (searchQuery) => {
    return students.filter(student => 
      student.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      student.class_id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      student.section.toLowerCase().includes(searchQuery.toLowerCase())
    );
  };

  useEffect(() => {
    fetchStudents();
    fetchClasses();
  }, []);

  return {
    students,
    setStudents,
    classes,
    sections,
    error,
    loading,
    fetchStudents,
    fetchClasses,
    addSection,
    addStudent,
    filterStudents
  };
};

export default useStudentData;
